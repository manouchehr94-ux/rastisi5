from django.shortcuts import render


def placeholder(request):
    return render(request, "core/placeholder.html")
