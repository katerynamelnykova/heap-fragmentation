from django.contrib import auth, messages
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import render, redirect
from django.urls import reverse_lazy, reverse
from django.views.generic.edit import FormMixin, UpdateView
from django.contrib.auth import login as auth_login, authenticate
from django.views.generic import ListView, DetailView
from .models import Post, Answer, KeyWords, MyUser
from .forms import PostForm, AnswerForm, SignUpForm, LoginForm, UsernameChangeForm, DeleteUserForm, ChangePasswordForm


class MainPage(ListView):
    """
    Return reversed list of added posts.
    """
    model = Post
    paginate_by = 10
    queryset = Post.objects.order_by('-id')
    template_name = "advice_app/index.html"


class Search(ListView):
    """
    Return list of posts that the user is looking for.
    """
    model = Post
    template_name = 'advice_app/search.html'
    paginate_by = 10

    def get_queryset(self):
        search_query = self.request.GET.get('search', '')
        search_list = search_query.split()
        search_result = []

        for keyword_user_wants in search_list:
            keyword_user_wants = KeyWords.remove_punctuation(keyword_user_wants)
            if KeyWords.is_key_word(keyword_user_wants):
                db_contains_keyword = KeyWords.objects.filter(word=keyword_user_wants).exists()
                if not db_contains_keyword:
                    new_word = KeyWords(word=keyword_user_wants)
                    new_word.save()
                else:
                    new_word = KeyWords.objects.get(word=keyword_user_wants)

                relevant_posts = Post.objects.filter(
                    Q(title__icontains=keyword_user_wants) |
                    Q(question__icontains=keyword_user_wants)
                )
                if not relevant_posts:
                    relevant_posts = Post.objects.filter(
                        Q(title__icontains=KeyWords.translate(keyword_user_wants)) |
                        Q(question__icontains=KeyWords.translate(keyword_user_wants))
                    )

                for post in relevant_posts:
                    new_word.posts.add(post.id)
                    if post not in search_result:
                        search_result.append(post)

        return search_result


class MyPosts(ListView):
    """
    Return reversed list of user's posts.
    """
    Model = Post
    template_name = "advice_app/my_posts.html"
    paginate_by = 10

    def get_queryset(self):
        return Post.objects.filter(author=self.request.user).order_by('-id')


def delete_post(request, pk=None):
    """
    Delete post by its id.

    :param pk: post id
    :type pk: int

    :return: redirect to the main page
    """
    post_to_delete = Post.objects.get(id=pk)
    post_to_delete.delete()
    return HttpResponseRedirect(reverse('index'))


def delete_answer(request, pk=None):
    """
    Delete answer by its id.

    :param pk: answer id
    :type pk: int

    :return: redirect to the connected post's detail page
    """
    page = request.META.get('HTTP_REFERER')
    answer_to_delete = Answer.objects.get(id=pk)
    answer_to_delete.delete()
    return redirect(page)


def change_password(request):
    """Password change function."""
    if request.method == 'POST':
        user = MyUser.objects.get(id=request.user.id)
        old_password = request.POST['password']
        if authenticate(username=user.username, password=old_password):
            new_password1 = request.POST['password1']
            new_password2 = request.POST['password2']
            if new_password1 == new_password2:
                user.set_password(new_password1)
                user.save()
                auth_login(request, user)
                return redirect('index')
            messages.add_message(request, messages.INFO, "Паролі не збігаються")
        else:
            messages.add_message(request, messages.INFO, "Пароль неправильний")

    form = ChangePasswordForm()
    return render(request, 'advice_app/change_password.html', {'form': form})


def delete_user(request):
    """User deletion function."""
    if request.method == 'POST':
        user = MyUser.objects.get(id=request.user.id)
        password = request.POST['password']
        if authenticate(username=user.username, password=password):
            user.delete()
            return redirect('index')
        messages.add_message(request, messages.INFO, "Пароль неправильний")

    form = DeleteUserForm()
    return render(request, 'advice_app/delete_user.html', {'form': form})


def change_status(request, pk=None):
    """
    Change post's status.

    :param pk: post id
    :type pk: int

    :return: redirect to the post's detail page
    """
    page = request.META.get('HTTP_REFERER')
    post = Post.objects.get(id=pk)
    post.isClosed = not post.isClosed
    post.save()
    return redirect(page)


class PostDetail(FormMixin, DetailView):
    """
    Return post's detail page.

    Post's detail page contains all information about post; extra author's functions: edit, mark as done, delete;
    Form of adding an answer; reversed list of answers.
    """
    model = Post
    template_name = "advice_app/detail.html"
    form_class = AnswerForm

    def get_success_url(self, **kwargs):
        return reverse_lazy('detail', kwargs={'pk':self.get_object().id})

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.post = self.get_object()
        self.object.author = MyUser.objects.get(id=self.request.user.id)
        self.object.save()
        return super().form_valid(form)

    def post(self, request, *args, **kwargs):
        page = request.META.get('HTTP_REFERER')
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return redirect(page)


class EditPost(UpdateView):
    """Edit post."""
    model = Post
    form_class = PostForm
    template_name = 'advice_app/edit.html'


class EditAnswer(UpdateView):
    """Edit answer."""
    model = Answer
    form_class = AnswerForm
    template_name = 'advice_app/edit_answer.html'


def edit_username(request):
    """Edit username."""
    if request.method == 'POST':
        user = request.user
        new_username = request.POST['username'].strip()
        if not MyUser.objects.filter(username=new_username) and new_username:
            user.username = new_username
            user.save()
            return redirect('index')
        messages.add_message(request, messages.INFO, "Дане ім'я вже зайняте")

    form = UsernameChangeForm()
    return render(request, 'advice_app/edit_username.html', {'form': form})


def increase_rating(request, pk=None):
    """
    Increase the rating of both the post and the user.

    When the user increases the rating of the answer, the rating of its author increases too.

    :param pk: answer id
    :type pk: int

    :return: redirect to the current page
    """
    page = request.META.get('HTTP_REFERER')
    user = Answer.objects.get(id=pk).author
    answer = Answer.objects.get(id=pk)

    has_user_increased_rating_previously = MyUser.objects.get(id=request.user.id) in answer.users_increased_rating.all()

    if not has_user_increased_rating_previously:
        has_user_decreased_rating_previously = MyUser.objects.get(id=request.user.id) in answer.users_decreased_rating.all()

        if has_user_decreased_rating_previously:
            # The user has previously decreased this answer's rating (-1), but is now increasing it (+1).
            # So, it is as if the user has not done anything at all, and so should be allowed to rate this answer again
            # in the future.

            # So, reset the user's restriction to decrease this answer's rating.
            user_to_delete = answer.users_decreased_rating
            user_to_delete.remove(MyUser.objects.get(id=request.user.id))
        else:
            answer.users_increased_rating.add(request.user.id)

        user.rating += 1
        user.save()
        answer.rating += 1
        answer.save()
    return redirect(page)


def decrease_rating(request, pk=None):
    """
    Decrease the rating of both the post and the user.

    When the user decreases the rating of the answer, the rating of its author decreases too.

    :param pk: answer id
    :type pk: int

    :return: redirect to the current page
    """
    page = request.META.get('HTTP_REFERER')
    user = Answer.objects.get(id=pk).author
    answer = Answer.objects.get(id=pk)

    has_user_decreased_rating_previously = MyUser.objects.get(id=request.user.id) in answer.users_decreased_rating.all()

    if not has_user_decreased_rating_previously:
        has_user_increased_rating_previously = MyUser.objects.get(id=request.user.id) in answer.users_increased_rating.all()

        if has_user_increased_rating_previously:
            # The user has previously increased this answer's rating (+1), but is now increasing it (-1).
            # So, it is as if the user has not done anything at all, and so should be allowed to rate this answer again
            # in the future.

            # So, reset the user's restriction to increase this answer's rating.
            user_to_delete = answer.users_increased_rating
            user_to_delete.remove(MyUser.objects.get(id=request.user.id))
        else:
            answer.users_decreased_rating.add(request.user.id)

        user.rating -= 1
        user.save()
        answer.rating -= 1
        answer.save()
    return redirect(page)


def add_post(request):
    """
    Add a new post.

    :return: template combined with context dictionary
    """
    error = ''
    if request.method == "POST":
        form = PostForm(request.POST)
        if form.is_valid():
            new_post = form.save(commit=False)
            new_post.author = MyUser.objects.get(id=request.user.id)
            new_post.save()
            return redirect('index')
        error = 'Недійсна форма'

    form = PostForm()
    context = {
        'form': form,
        'error': error
    }
    return render(request, 'advice_app/add_post.html', context)


def register(request):
    """
    Create a new account and login.

    :return: template combined with context dictionary
    """
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()
            username = form.cleaned_data.get('username')
            raw_password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=raw_password)
            auth_login(request, user)
            return redirect('index')
        messages.add_message(request, messages.INFO, "Форма недійсна. Змініть ім'я або пароль")
        messages.add_message(request, messages.INFO,
                             "Пароль має бути довше 8 символів та містити не лише числа")
    else:
        form = SignUpForm()
    return render(request, 'advice_app/register.html', {'form': form})


def login(request):
    """
    Login to an existing account.

    :return: template combined with context dictionary
    """
    if request.method == 'POST':
        form = LoginForm(request, request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                auth_login(request, user)
                return redirect('index')
        messages.add_message(request, messages.INFO, "Недійсне ім'я або пароль")
    form = LoginForm()
    return render(request, 'advice_app/login.html', {'form': form})


def logout(request):
    """
    Logout the user.

    :return: redirect to the main page
    """
    auth.logout(request)
    return redirect('index')


class GuestPosts(ListView):
    """
    Shows shows posts to unregistered users
    """
    model = Post
    paginate_by = 10
    queryset = Post.objects.order_by('-id')
    template_name = "advice_app/recent_posts.html"
