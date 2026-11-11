from rest_framework.permissions import BasePermission


class IsBusinessStaff(BasePermission):
    """Allows signed-in users who belong to a business (have a StaffProfile)."""

    message = "Your account isn't linked to a business."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and hasattr(user, "staff"))


def business_for(request):
    return request.user.staff.business
