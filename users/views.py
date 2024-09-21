from django.contrib.auth.models import User
from rest_framework import generics, status, permissions, throttling
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import api_view, throttle_classes
from django.db import transaction
from .models import FriendRequest
from django.contrib.auth.models import User
from rest_framework import generics
from .serializers import UserSerializer, FriendRequestSerializer
from rest_framework import permissions
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.decorators import authentication_classes, permission_classes
from django.views.decorators.csrf import csrf_exempt
from django.contrib.postgres.search import SearchVector, SearchQuery
from rest_framework.pagination import PageNumberPagination

class SignupView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]

class LoginThrottle(throttling.UserRateThrottle):
    rate = '5/min'  # Limit login attempts to 5 per minute


from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        # Perform login, validate credentials
        username = request.data.get("email")
        password = request.data.get("password")
        try:
            user = User.objects.get(email__iexact=username)  # email is case-insensitive
            if user.check_password(password):
                refresh = RefreshToken.for_user(user)
                return Response({
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                })
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)
        except User.DoesNotExist:
            return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)




### Role-Based Access Control (RBAC)
class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_staff

class IsReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS


### User Search View

class UserPagination(PageNumberPagination):
    page_size = 10  # Set the number of records per page
    page_size_query_param = 'page_size'
    max_page_size = 100  # Optional: to limit max size for the user

class UserSearchView(generics.ListAPIView):
    serializer_class = UserSerializer
    pagination_class = UserPagination
    # Uncomment the next line to require authentication
    # permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        query = self.request.query_params.get('q')
        if query:
            # Use full-text search for names
            name_search = (
                User.objects.annotate(
                    search=SearchVector('first_name', 'last_name')
                ).filter(search=SearchQuery(query))
            )
            email_search = User.objects.filter(email__icontains=query)

            return name_search | email_search

        return User.objects.none()

### Friend Request Management

from rest_framework import permissions


@api_view(['POST'])
@throttle_classes([throttling.UserRateThrottle])  # Limit requests to prevent spam
@authentication_classes([JWTAuthentication])  # Use JWT authentication here
@permission_classes([IsAuthenticated])  # Ensure user is authenticated
def send_friend_request(request):
    to_user_id = request.data.get("to_user")

    if request.user.is_anonymous:
        return Response({"error": "User must be logged in to send friend requests"},
                        status=status.HTTP_401_UNAUTHORIZED)

    try:
        with transaction.atomic():  # Ensure atomicity
            to_user = User.objects.get(id=to_user_id)
            FriendRequest.objects.create(from_user=request.user, to_user=to_user, status='pending')
            return Response({"message": "Friend request sent"}, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({"error": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@csrf_exempt
def accept_friend_request(request, request_id):
    try:
        with transaction.atomic():
            # Only allow the request if the authenticated user is the 'to_user' in the friend request
            friend_request = FriendRequest.objects.get(id=request_id, to_user=request.user)
            friend_request.status = 'accepted'
            friend_request.save()
            return Response({"message": "Friend request accepted"}, status=status.HTTP_200_OK)
    except FriendRequest.DoesNotExist:
        return Response({"error": "Friend request not found"}, status=status.HTTP_404_NOT_FOUND)


@api_view(['POST'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
@csrf_exempt
def reject_friend_request(request, request_id):
    try:
        with transaction.atomic():
            friend_request = FriendRequest.objects.get(id=request_id, to_user=request.user)
            friend_request.status = 'rejected'
            friend_request.save()
            return Response({"message": "Friend request rejected"}, status=status.HTTP_200_OK)
    except FriendRequest.DoesNotExist:
        return Response({"error": "Friend request not found"}, status=status.HTTP_404_NOT_FOUND)


### Friend List View

class FriendsListView(generics.ListAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]  # Ensure that only authenticated users can access this
    authentication_classes = [JWTAuthentication]  # Use JWT authentication

    def get_queryset(self):
        # Get friends where status is 'accepted'
        return User.objects.filter(
            sent_requests__to_user=self.request.user, sent_requests__status='accepted'
        ).select_related('profile')


### Pending Friend Requests View

class PendingFriendRequestsView(generics.ListAPIView):
    serializer_class = FriendRequestSerializer
    authentication_classes = [JWTAuthentication]  # Use JWT authentication here
    permission_classes = [permissions.IsAuthenticated]  # Ensure user is authenticated

    def get_queryset(self):
        if self.request.user.is_authenticated:
            print(f"Authenticated user: {self.request.user}")
            return FriendRequest.objects.filter(to_user=self.request.user, status='pending').order_by('-created_at')
        else:
            return Response({"error": "User not authenticated"}, status=status.HTTP_401_UNAUTHORIZED)


### User Activity Logging (via Django signals)

# Use Django signals to log friend request activities like 'sent', 'accepted', etc.
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ActivityLog

@receiver(post_save, sender=FriendRequest)
def log_friend_request_activity(sender, instance, created, **kwargs):
    if created:
        ActivityLog.objects.create(
            user=instance.from_user,
            action=f"Sent friend request to {instance.to_user}"
        )
    elif instance.status == 'accepted':
        ActivityLog.objects.create(
            user=instance.to_user,
            action=f"Accepted friend request from {instance.from_user}"
        )
