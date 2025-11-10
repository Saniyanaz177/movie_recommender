from django.contrib.auth import authenticate, login
from django.contrib.auth import logout
from django.shortcuts import render, get_object_or_404, redirect
from .forms import *
from django.http import Http404
from .models import Movie, Myrating, MyList
from django.db.models import Q
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.db.models import Case, When
import pandas as pd

# Create your views here.

def index(request):
    movies = Movie.objects.all()
    query = request.GET.get('q')

    if query:
        movies = Movie.objects.filter(Q(title__icontains=query)).distinct()
        return render(request, 'recommend/list.html', {'movies': movies})

    return render(request, 'recommend/list.html', {'movies': movies})


# Show details of the movie
def detail(request, movie_id):
    if not request.user.is_authenticated:
        return redirect("login")
    if not request.user.is_active:
        raise Http404
    movies = get_object_or_404(Movie, id=movie_id)
    movie = Movie.objects.get(id=movie_id)
    
    temp = list(MyList.objects.all().values().filter(movie_id=movie_id,user=request.user))
    if temp:
        update = temp[0]['watch']
    else:
        update = False
    if request.method == "POST":

        # For my list
        if 'watch' in request.POST:
            watch_flag = request.POST['watch']
            if watch_flag == 'on':
                update = True
            else:
                update = False
            if MyList.objects.all().values().filter(movie_id=movie_id,user=request.user):
                MyList.objects.all().values().filter(movie_id=movie_id,user=request.user).update(watch=update)
            else:
                q=MyList(user=request.user,movie=movie,watch=update)
                q.save()
            if update:
                messages.success(request, "Movie added to your list!")
            else:
                messages.success(request, "Movie removed from your list!")

            
        # For rating
        else:
            rate = request.POST['rating']
            if Myrating.objects.all().values().filter(movie_id=movie_id,user=request.user):
                Myrating.objects.all().values().filter(movie_id=movie_id,user=request.user).update(rating=rate)
            else:
                q=Myrating(user=request.user,movie=movie,rating=rate)
                q.save()

            messages.success(request, "Rating has been submitted!")

        return HttpResponseRedirect(request.META.get('HTTP_REFERER'))
    out = list(Myrating.objects.filter(user=request.user.id).values())

    # To display ratings in the movie detail page
    movie_rating = 0
    rate_flag = False
    for each in out:
        if each['movie_id'] == movie_id:
            movie_rating = each['rating']
            rate_flag = True
            break

    context = {'movies': movies,'movie_rating':movie_rating,'rate_flag':rate_flag,'update':update}
    return render(request, 'recommend/detail.html', context)


# MyList functionality
def watch(request):

    if not request.user.is_authenticated:
        return redirect("login")
    if not request.user.is_active:
        raise Http404

    movies = Movie.objects.filter(mylist__watch=True,mylist__user=request.user)
    query = request.GET.get('q')

    if query:
        movies = Movie.objects.filter(Q(title__icontains=query)).distinct()
        return render(request, 'recommend/watch.html', {'movies': movies})

    return render(request, 'recommend/watch.html', {'movies': movies})


# To get similar movies based on user rating
def get_similar(movie_name,rating,corrMatrix):
    similar_ratings = corrMatrix[movie_name]*(rating-2.5)
    similar_ratings = similar_ratings.sort_values(ascending=False)
    return similar_ratings

# Recommendation Algorithm
def recommend(request):
    if not request.user.is_authenticated:
        return redirect("login")
    if not request.user.is_active:
        raise Http404

    # Get all user ratings
    movie_rating = pd.DataFrame(list(Myrating.objects.all().values()))

    if movie_rating.empty:
        messages.warning(request, "No ratings found in the system yet.")
        return render(request, 'recommend/recommend.html', {'movie_list': []})

    # Identify new user
    new_user_count = movie_rating.user_id.nunique()
    current_user_id = request.user.id

    # Add a dummy rating for new users to avoid empty DataFrame
    if current_user_id > new_user_count:
        movie = Movie.objects.first()
        Myrating.objects.create(user=request.user, movie=movie, rating=0)

    # Create pivot table
    userRatings = movie_rating.pivot_table(index='user_id', columns='movie_id', values='rating').fillna(0)
    if userRatings.shape[1] < 2:
        messages.info(request, "Not enough ratings to generate recommendations.")
        return render(request, 'recommend/recommend.html', {'movie_list': []})

    # Compute correlation matrix
    corrMatrix = userRatings.corr(method='pearson')

    # Get current user's ratings
    user = pd.DataFrame(list(Myrating.objects.filter(user=request.user).values())).drop(['user_id','id'], axis=1)
    user_filtered = [tuple(x) for x in user.values]
    movie_id_watched = [each[0] for each in user_filtered]

    # Initialize recommendations
    similar_movies = pd.Series(dtype='float64')

    # Aggregate similar movies based on correlations
    for movie_id, rating in user_filtered:
        if movie_id in corrMatrix.columns:
            score = corrMatrix[movie_id] * (rating - 2.5)
            similar_movies = similar_movies.add(score, fill_value=0)

    if similar_movies.empty:
        messages.warning(request, "No similar movies found for your rated titles.")
        return render(request, 'recommend/recommend.html', {'movie_list': []})

    # Sort recommendations
    similar_movies = similar_movies.sort_values(ascending=False)

    # Filter out movies already watched
    movies_id_recommend = [m for m in similar_movies.index if m not in movie_id_watched]

    # Get top 10 movies
    preserved = Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(movies_id_recommend)])
    movie_list = list(Movie.objects.filter(id__in=movies_id_recommend).order_by(preserved)[:10])

    context = {'movie_list': movie_list}
    return render(request, 'recommend/recommend.html', context)


# Register user
def signUp(request):
    form = UserForm(request.POST or None)

    if form.is_valid():
        user = form.save(commit=False)
        username = form.cleaned_data['username']
        password = form.cleaned_data['password']
        user.set_password(password)
        user.save()
        user = authenticate(username=username, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect("index")

    context = {'form': form}

    return render(request, 'recommend/signUp.html', context)


# Login User
def Login(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(username=username, password=password)

        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect("index")
            else:
                return render(request, 'recommend/login.html', {'error_message': 'Your account disable'})
        else:
            return render(request, 'recommend/login.html', {'error_message': 'Invalid Login'})

    return render(request, 'recommend/login.html')


# Logout user
def Logout(request):
    logout(request)
    return redirect("login")
