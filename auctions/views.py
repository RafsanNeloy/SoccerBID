from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required,user_passes_test
from django.db.models import Count, Q
from django.http import  HttpResponseRedirect, Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.db import connections
from .models import User, Listing, Watch, Bid, Comment
from .forms import ListingForm
from .utils import *
from django.utils import timezone
# from datetime import timedelta
import random
from django.core.mail import send_mail
from django.contrib.auth.hashers import make_password
import time, datetime, calendar
from django.template.loader import render_to_string
from django.contrib.admin.views.decorators import staff_member_required


def index(request):
    listings = Listing.objects.filter(auction_active=True)
    for listing in listings:
        listing.starting_value = get_current_bid_value(listing.id)
        # listing.remaining_time = max(listing.end_time - timezone.now(), timedelta(seconds=0))
    return render(request, "auctions/index.html", {
        "listings": listings
    })


def login_view(request):
    if request.method == "POST":

        # Attempt to sign user in
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        
        if username == 'admin' and user is not None:
            login(request,user)
            return HttpResponseRedirect(reverse("admin_view"))

        # Check if authentication successful
        if user is not None:
            login(request, user)
            return HttpResponseRedirect(reverse("index"))
        else:
            return render(request, "auctions/authentication/login.html", {
                "message": "Invalid username and/or password."
            })
    else:
        return render(request, "auctions/authentication/login.html")


def logout_view(request):
    logout(request)
    return HttpResponseRedirect(reverse("index"))


def register(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirmation = request.POST.get('confirmation')

        # Check if username already exists
        if User.objects.filter(username=username).exists():
            return render(request, 'auctions/authentication/register.html', {'message': 'Username already exists'})

        # Basic validation
        if password == confirmation:
            # Generate OTP
            otp = random.randint(100000, 999999)
            
            # Store registration data and OTP in session
            request.session['username'] = username
            request.session['email'] = email
            request.session['password'] = password
            request.session['otp'] = otp
            
            # Send OTP via email
            html_content = render_to_string('auctions/mail/otp_mail.html', {
                'username': username,
                'otp': otp
            })
            
            try:
                send_mail(
                    'Your Account Verification OTP',
                    'Use the following OTP to verify your account:',
                    'soccer.auction2024@gmail.com',  # Update with your email
                    [email],
                    html_message=html_content,
                    fail_silently=False,
                )
                return redirect('otp_verification')
            except Exception as e:
                return render(request, 'auctions/authentication/register.html', 
                            {'message': 'Failed to send OTP. Please try again.'})
        else:
            return render(request, 'auctions/authentication/register.html', 
                        {'message': 'Passwords do not match'})

    return render(request, 'auctions/authentication/register.html')

def otp_verification(request):
    if request.method == 'POST':
        user_otp = request.POST.get('otp')
        if int(user_otp) == request.session.get('otp', 0):
            # Create user if OTP verification succeeds
            user = User.objects.create(
                username=request.session['username'],
                email=request.session['email'],
                password=make_password(request.session['password'])
            )
            user.save()
            
            # Clean up session data
            del request.session['username']
            del request.session['email']
            del request.session['password']
            del request.session['otp']
            
            messages.success(request, 'Account created successfully. Please log in.')
            return redirect('login')
        else:
            return render(request, 'auctions/authentication/otp_authentication.html', 
                        {'error': 'Invalid OTP'})
    return render(request, 'auctions/authentication/otp_authentication.html')



def otp_success(request):
    # Redirect to login page after 5 seconds
    time.sleep(5)
    return redirect('login')

def forgot_password(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        
        # Check if user exists
        user = User.objects.get(username=username, email=email)
        
        if user is not None:
            # Generate OTP
            otp = random.randint(100000, 999999)
            
            request.session['otp'] = otp
            request.session['username'] = username
            request.session['email'] = email
            
            html_content = render_to_string('auctions/mail/forgot_password_mail.html', {'username': username, 'otp': otp})
            # Send OTP via email
            try:
                send_mail(
                    'Your Account Verification OTP',
                    'Use the following OTP to verify your account:',
                    'soccerbid@gmail.com',
                    [email],
                    html_message=html_content,
                    fail_silently=False,
                )
            except Exception as e:
                return render(request, 'auctions/authentication/forgot_password.html', {'message': 'Failed to send email. Please try again later.'})
            
            return redirect('password_otp')
        else:
            return render(request, 'auctions/authentication/forgot_password.html', {'message': 'Invalid username and/or email.'})
        
    return render(request, 'auctions/authentication/forgot_password.html')

def password_otp(request):
    if request.method == 'POST':
        user_otp = request.POST.get('otp')
        
        # Check if OTP is provided
        if user_otp is None:
            return render(request, 'auctions/authentication/otp_authentication.html', {'error': 'OTP is required'})
        
        # Check if OTP is a valid integer
        try:
            otp = int(user_otp)
        except ValueError:
            return render(request, 'auctions/authentication/otp_authentication.html', {'error': 'Invalid OTP format'})
        
        # Check OTP against session OTP
        if otp == request.session.get('otp', 0):
            # Set a session variable to indicate OTP verification success
            request.session['otp_verified'] = True
            
            username = request.session['username']
            email = request.session['email']
            
            # Generate a new password
            password = User.objects.make_random_password()
            user = User.objects.get(username=username, email=email)
            user.set_password(password)
            user.save()
            
            html_content = render_to_string('auctions/mail/new_password_mail.html', {'username': username, 'password': password})
            
            send_mail(
                'Your Account Verification OTP',
                'Use the following OTP to verify your account:',
                'soccerbid2025@gmail.com',
                [email],
                html_message=html_content,
                fail_silently=False,
            )
            
            return redirect('password_reset_success')  # Redirect to the success page
        else:
            return render(request, 'auctions/authentication/otp_authentication.html', {'error': 'Invalid OTP'})
        
    return render(request, 'auctions/authentication/otp_authentication.html')

def password_reset_success(request):
    return render(request, 'auctions/authentication/password_reset_successful.html')

@login_required(redirect_field_name='index')
def create_listing(request):
    if not request.user.is_authenticated:
        return HttpResponseRedirect(reverse("index"))

    if request.method == "POST":
        form = ListingForm(request.POST, request.FILES)
        if form.is_valid():
            listing = Listing(
                user=request.user,
                title=form.cleaned_data["title"],
                category=form.cleaned_data["category"],
                description=form.cleaned_data["description"],
                starting_value=form.cleaned_data["starting_value"],
                image=form.cleaned_data["image"]
            )
            listing.save()
            message = f"Your listing {listing.title} has been created successfully."
            messages.success(request, message)
            return redirect("index")
        else:
            return render(request, "auctions/createListing.html", {'form': form})

    return render(request, "auctions/createListing.html", {'form': ListingForm})

def view_listing(request, listing_id, error_message=None):
    listing = Listing.objects.get(id=listing_id)
    
    # Get the last 10 bids for this listing, ordered by most recent first
    bid_history = Bid.objects.filter(listing_id=listing_id).order_by('-created_at')[:10]
    
    isActive = listing.auction_active
    current_bid = get_current_bid_value(listing_id)
    highest_bidder = get_current_bidder(listing_id)
    # listing.remaining_time = max(listing.end_time - timezone.now(), timedelta(seconds=0))

    user_authenticated = request.user.is_authenticated
    if (user_authenticated):    
        watchExists = Watch.objects.filter(user=request.user, listing=listing_id).exists()
        isOwner = listing.user == request.user
    else:
        watchExists=False
        isOwner = False

    if not(error_message):
        return render(request, "auctions/listingView.html", {
            'user_authenticated': user_authenticated,
            'listing': listing,
            'watch': watchExists,
            'current_bid': current_bid,
            'owner': isOwner,
            'active': isActive,
            'comments': Comment.objects.filter(listing=listing),
            'highest_bidder': highest_bidder,
            # 'remaining_time': listing.remaining_time,
            'bid_history': bid_history,
        })
    else:
        return render(request, "auctions/listingView.html", {
            'user_authenticated': user_authenticated,
            'listing': listing,
            'watch': watchExists,
            'current_bid': current_bid,
            'owner': isOwner,
            'active': isActive,
            'comments': Comment.objects.filter(listing=listing),
            'highest_bidder': highest_bidder,
            # 'remaining_time': listing.remaining_time,
            'error_message': 'Your bid was too Low',
        })

@login_required(redirect_field_name='index')
def watch(request, listing_id):
    # if the user is not watching the item it will add a watch to the item. If the user is already watching the item it will delete the watch from the item.
    watch = Watch.objects.filter(user=request.user, listing_id=listing_id)
    if watch.exists():
        watch.delete()
    else:
        watch = Watch(user=request.user, listing_id=listing_id)
        watch.save()
    
    return HttpResponseRedirect(reverse("listing", args=(listing_id,)))

@login_required(redirect_field_name='index')
def bid(request, listing_id):
    current_bid = get_current_bid_value(listing_id)
    listing = Listing.objects.get(id=listing_id)

    if float(request.POST["value"]) > current_bid:
        newBid = Bid(user=request.user, listing_id=listing_id, value=request.POST["value"])
        newBid.save()

        # Update the winner of the listing to the current highest bidder
        bids = Bid.objects.filter(listing_id=listing_id)
        if bids.exists():
            highest_bid = bids.order_by('-value')[0]
            listing.winner = highest_bid.user
            listing.save()

        return HttpResponseRedirect(reverse("listing", args=(listing_id,)))

    else:
        return view_listing(request, listing_id, error_message=True)

@login_required(redirect_field_name='index')
def close_auction(request, listing_id):
    # TODO if no one has bid
    listing = Listing.objects.get(id=listing_id)
    listing.auction_active = False

    # set the highest bid to the winner of the bid
    bids = Bid.objects.filter(listing_id=listing_id)
    if bids.exists():
        highest_bid = bids.order_by('value')[0]
        listing.winner = highest_bid.user
    else:
        listing.winner = None

    listing.save()
    return HttpResponseRedirect(reverse("listing", args=(listing_id,)))

@login_required(redirect_field_name='index')
def comment(request, listing_id):
    comment = request.POST['comment']
    comment = Comment(user=request.user, listing_id = listing_id, comment=comment)
    comment.save()
    return HttpResponseRedirect(reverse("listing", args=(listing_id,)))

@login_required(redirect_field_name='index')
def your_listings(request):
    listings = Listing.objects.filter(user=request.user)
    
    for listing in listings:
        listing.starting_value = get_current_bid_value(listing.id)
    
    return render(request, "auctions/profile/yourListings.html", {
        'listings': listings,
    })

@login_required(redirect_field_name='index')
def won_listings(request):
    
    listings = Listing.objects.filter(winner=request.user)
    
    for listing in listings:
        listing.starting_value = get_current_bid_value(listing.id)
    
    return render(request, "auctions/profile/wonListings.html", {
        'listings': listings,
    })

@login_required(redirect_field_name='index')
def watch_list(request):
    listings = Listing.objects.raw(f'SELECT * FROM auctions_listing, auctions_watch WHERE auctions_listing.id = auctions_watch.listing_id AND auctions_watch.user_id=%s', [request.user.id])
    return render(request, "auctions/profile/watchList.html", {
        'listings': listings
    })

def categories(request):
    with connections['default'].cursor() as cursor:
        cursor.execute("SELECT DISTINCT category FROM auctions_listing ORDER BY category")
        cats = cursor.fetchall() #list of tuples returned

    # converting the list of tuples to just a list
    categories = []
    for category in cats:
        categories.append(category[0])

    return render(request, "auctions/categories.html", {
        'categories': categories
    }

    )
def index(request):
    # Fetch categories for the home page slider
    with connections['default'].cursor() as cursor:
        cursor.execute("SELECT DISTINCT category FROM auctions_listing ORDER BY category")
        cats = cursor.fetchall()  # list of tuples returned
    
    # Converting the list of tuples to just a list
    categories = [category[0] for category in cats]

    # Fetch recent listings for the home page
    listings = Listing.objects.all()  # You can adjust this as needed
    
    return render(request, "auctions/index.html", {
        'categories': categories,
        'listings': listings,
    })


def category(request, category):
    active_listings = Listing.objects.filter(category=category, auction_active=True)
    inactive_listings = Listing.objects.filter(category=category, auction_active=False)
    
    for listing in active_listings:
        listing.starting_value = get_current_bid_value(listing.id)
    
    for listing in inactive_listings:
        listing.starting_value = get_current_bid_value(listing.id)
    
    return render(request, "auctions/category.html",{
        'category': category,
        'active_listings': active_listings,
        'inactive_listings': inactive_listings,
    })


@login_required
def view_profile(request):
    user = request.user
    return render(request, "auctions/profile/view_profile.html", {'user': user})

@login_required
def edit_profile(request):
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST['first_name']
        user.last_name = request.POST['last_name']
        user.email = request.POST['email']
        user.address = request.POST.get('address', '')  # Use get() method to handle cases where address is not provided

        # Handle profile picture upload
        if 'profile_picture' in request.FILES:
            user.profile_picture = request.FILES['profile_picture']

        user.save()
        return HttpResponseRedirect(reverse('view_profile'))
    return render(request, 'auctions/profile/edit_profile.html', {'user': request.user})


@login_required
def edit_password(request):
    if request.method == 'POST':
        user = request.user
        original_password = request.POST['original_password']
        new_password = request.POST['new_password']
        confirm_password = request.POST['confirm_password']
        
        # Check if the original password provided by the user is correct
        if authenticate(username=user.username, password=original_password):
            # Check if the new password and confirmation match
            if new_password == confirm_password:
                user.set_password(new_password)
                user.save()
                return HttpResponseRedirect(reverse('view_profile'))
            else:
                return render(request, 'auctions/profile/edit_password.html', {'error': 'New passwords do not match'})
        else:
            return render(request, 'auctions/profile/edit_password.html', {'error': 'Invalid original password'})

    return render(request, 'auctions/profile/edit_password.html')

def is_superuser(user):
    # Check if the user is a superuser
    return user.is_superuser

@user_passes_test(is_superuser, login_url='/forbidden/')
def admin_view(request):
    
    users = User.objects.all()
    listings = Listing.objects.all()
    total_users = User.objects.count()
    total_listings = Listing.objects.count()
    active_listings = Listing.objects.filter(auction_active=True).count()
    inactive_listings = Listing.objects.filter(auction_active=False).count()
            
    context = {
        'users': users,
        'listings': listings,
        'total_users': total_users,
        'total_listings': total_listings,
        'active_listings': active_listings,
        'inactive_listings': inactive_listings,
    }
    return render(request, 'auctions/admin/admin_dashboard.html', context)

@user_passes_test(is_superuser, login_url='/forbidden/')
def manage_users(request):
    users = User.objects.all()
    return render(request, 'auctions/admin/manage_users.html', {'users': users})

@staff_member_required
def manage_listings(request):
    query = request.GET.get('q', '')
    listings = Listing.objects.all()
    
    if query:
        listings = listings.filter(
            Q(title__icontains=query) | 
            Q(description__icontains=query) | 
            Q(category__icontains=query)
        )
    
    # Add a method to get current bid value for each listing
    for listing in listings:
        listing.current_bid = get_current_bid_value(listing.id)
    
    return render(request, "auctions/admin/manage_listings.html", {
        "listings": listings
    })

@staff_member_required
def delete_listing_ajax(request, listing_id):
    if request.method == 'POST':
        try:
            listing = get_object_or_404(Listing, id=listing_id)
            listing.delete()
            return JsonResponse({
                'status': 'success', 
                'message': 'Listing deleted successfully'
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error', 
                'message': str(e)
            }, status=400)

@staff_member_required
def toggle_listing_status_ajax(request, listing_id):
    if request.method == 'POST':
        try:
            listing = get_object_or_404(Listing, id=listing_id)
            listing.auction_active = not listing.auction_active
            listing.save()
            return JsonResponse({
                'status': 'success', 
                'message': 'Listing status updated successfully',
                'auction_active': listing.auction_active
            })
        except Exception as e:
            return JsonResponse({
                'status': 'error', 
                'message': str(e)
            }, status=400)

@user_passes_test(is_superuser, login_url='/forbidden/')
def deactivate_listing(request, listing_id):
    listing = get_object_or_404(Listing, pk=listing_id)
    if request.method == 'POST':
        listing.auction_active = False
        listing.save()
        return redirect('manage_listings')

@user_passes_test(is_superuser, login_url='/forbidden/')
def delete_listing(request, listing_id):
    try:
        listing = Listing.objects.get(pk=listing_id)
    except Listing.DoesNotExist:
        raise Http404("Listing does not exist")
    
    if request.method == 'POST':
        listing.delete()
        return redirect('manage_listings')  # Redirect to admin dashboard or any other desired page
    # Handle GET request if needed

@user_passes_test(is_superuser, login_url='/forbidden/')
def reports(request):
    # User Reports
    # Data for user-wise listings
    user_wise_listings = (
        User.objects.annotate(total_listings=Count('listings'))
        .values('username', 'total_listings')
    )
    
    # Data for user registration reports
    today = timezone.now().date()
    last_seven_days = today - timezone.timedelta(days=6)
    user_registration_data = (
        User.objects.filter(date_joined__date__range=[last_seven_days, today])
        .values('date_joined__date')
        .annotate(total_registrations=Count('id'))
    )
    
    # Data for user registration reports (last 3 months)
    this_month = today.replace(day=1)
    last_three_months = [this_month - timezone.timedelta(days=i*30) for i in range(3)]
    
    user_registration_data_3_months = (
        User.objects.filter(date_joined__date__range=[last_three_months[2], today])
        .values('date_joined__month')
        .annotate(total_registrations=Count('id'))
    )
    
    # Listings created in the last 7 days
    today = timezone.now().date()
    last_week = today - timezone.timedelta(days=6)
    day_wise_listings = (
        Listing.objects.filter(created_at__date__range=[last_week, today])
        .values('created_at__date')
        .annotate(count=Count('id'))
    )
    
    # Listings created in the last 3 months
    this_month = today.replace(day=1)
    last_three_months = [this_month - timezone.timedelta(days=i*30) for i in range(3)]
    month_wise_listings = (
        Listing.objects.filter(created_at__date__range=[last_three_months[2], today])
        .values('created_at__month')
        .annotate(count=Count('id'))
    )
    month_names = [calendar.month_name[month['created_at__month']] for month in month_wise_listings]
    
    # Data for category reports
    category_data = (
        Listing.objects.values('category')
        .annotate(total_listings=Count('id'))
        .order_by('-total_listings')
    )
    
    #Bids Reports
    most_bid_item = Listing.objects.annotate(num_bids=Count('bids')).order_by('-num_bids').first()
    least_bid_item = Listing.objects.annotate(num_bids=Count('bids')).order_by('num_bids').first()
    # Query to get the top bidders
    top_bidders = User.objects.annotate(num_bids=Count('bids')).order_by('-num_bids')[:10]

    context = {
        'day_wise_listings': day_wise_listings,
        'month_wise_listings': month_wise_listings,
        'month_names': month_names,
        'user_wise_listings': user_wise_listings,
        'user_registration_data': user_registration_data,
        'user_registration_data_3_months': user_registration_data_3_months,
        'category_data': category_data,
        'most_bid_item': most_bid_item,
        'least_bid_item': least_bid_item,
        'top_bidders': top_bidders,
    }
    
    return render(request, 'auctions/admin/reports.html', context)

def forbidden_view(request):
    return render(request,"auctions/admin/forbidden.html")

@staff_member_required
def toggle_agent_status(request, user_id):
    if request.method == 'POST':
        user = get_object_or_404(User, id=user_id)
        user.is_agent = not user.is_agent
        user.save()
    return redirect('manage_users')

@login_required
def request_agent_status(request):
    if request.method == 'POST':
        # Mark the user as requesting agent status
        request.user.req_agent = True
        request.user.save()
        messages.success(request, 'Your request to become an agent has been submitted.')
        return redirect('view_profile')
    return redirect('view_profile')

@user_passes_test(is_superuser, login_url='/forbidden/')
def manage_agent_requests(request):
    # Get all users who have requested agent status
    agent_requests = User.objects.filter(req_agent=True, is_agent=False)
    return render(request, 'auctions/admin/manage_agent_requests.html', {'agent_requests': agent_requests})

@user_passes_test(is_superuser, login_url='/forbidden/')
def approve_agent_request(request, user_id):
    if request.method == 'POST':
        try:
            user = User.objects.get(id=user_id)
            user.is_agent = True
            user.req_agent = False
            user.save()
            
            # Optional: Send an email notification
            subject = 'Agent Status Approved'
            message = 'Your request to become an agent has been approved.'
            send_mail(
                subject,
                message,
                'soccer.auction2024@gmail.com',
                [user.email],
                fail_silently=False,
            )
            
            messages.success(request, f'Agent status approved for {user.username}')
        except User.DoesNotExist:
            messages.error(request, 'User not found')
    return redirect('manage_agent_requests')

@user_passes_test(is_superuser, login_url='/forbidden/')
def reject_agent_request(request, user_id):
    if request.method == 'POST':
        try:
            user = User.objects.get(id=user_id)
            user.req_agent = False
            user.save()
            
            # Optional: Send an email notification
            subject = 'Agent Status Request Rejected'
            message = 'Your request to become an agent has been rejected.'
            send_mail(
                subject,
                message,
                'soccer.auction2024@gmail.com',
                [user.email],
                fail_silently=False,
            )
            
            messages.success(request, f'Agent request rejected for {user.username}')
        except User.DoesNotExist:
            messages.error(request, 'User not found')
    return redirect('manage_agent_requests')

@user_passes_test(is_superuser, login_url='/forbidden/')
def delete_user(request, user_id):
    try:
        user = User.objects.get(pk=user_id)
        # Prevent deleting superusers
        if user.is_superuser:
            messages.error(request, 'Cannot delete a superuser account.')
            return redirect('manage_users')
        
        user.delete()
        messages.success(request, f'User {user.username} has been deleted successfully.')
    except User.DoesNotExist:
        messages.error(request, 'User not found.')
    
    return redirect('manage_users')