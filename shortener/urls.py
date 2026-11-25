"""shortener urls"""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("shorten", views.shorten, name="shorten"),
    path("shorten/", views.shorten),
    path("create/", views.create, name="create"),
    path("analytics/<str:url_id>", views.analytics, name="analytics"),
    path("analytics/<str:url_id>/", views.analytics),
    path("internal/cleanup", views.cleanup, name="cleanup"),
    path("internal/cleanup/", views.cleanup),
    path("<str:url_id>", views.url, name="url"),
    path("<str:url_id>/", views.url),
]
