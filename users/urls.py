from django.urls import path
from . import views

urlpatterns = [
    path('signup/', views.SignupView.as_view(), name='signup'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('search/', views.UserSearchView.as_view(), name='search'),
    path('friends/', views.FriendsListView.as_view(), name='friends-list'),
    path('friend-request/send/', views.send_friend_request, name='send-friend-request'),
    path('friend-request/accept/<int:request_id>/', views.accept_friend_request, name='accept-friend-request'),
    path('friend-request/reject/<int:request_id>/', views.reject_friend_request, name='reject-friend-request'),
    path('friend-request/pending/', views.PendingFriendRequestsView.as_view(), name='pending-friend-requests'),
]
