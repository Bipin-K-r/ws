from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

def health(request):
    return JsonResponse({"status": "ok"})

def ready(request):
    return JsonResponse({"ready": True})

def metrics(request):
    data = generate_latest()
    return HttpResponse(data, content_type=CONTENT_TYPE_LATEST)
