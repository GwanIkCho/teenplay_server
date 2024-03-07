from django.db.models import F, Q
from django.shortcuts import render, redirect
from django.views import View
from rest_framework.response import Response
from rest_framework.views import APIView

from member.models import Member
from teenplay_server.category import Category
from wishlist.models import Wishlist, WishlistReply


class WishListView(View):
    # 페이지 이동
    def get(self, request):
        return render(request, 'wishlist/web/wishlist-web.html')


class WishListWriteAPI(APIView):
    def post(self, request):
        data = request.data
        data = {
            'wishlist_content': data['wishlist-content'],
            'category': data['category'],
            'member_id': request.session['member']['id']
        }

        Wishlist.objects.create(**data)
        return Response('success')


class WishListAPI(APIView):
    def get(self, request, page):
        # 페이지당 3개의 게시물 보여주기
        row_count = 3
        offset = (page - 1) * row_count
        limit = page * row_count

        columns = [
            'wishlist_content',
            'member_name',
            'category_name',
            'created_date'
        ]

        wishlists = Wishlist.enabled_objects.annotate(member_name=F("member__member_nickname"),category_name=F("category__category_name")).values(*columns)

        return Response(wishlists[offset:limit])


class WishListCategoryAPI(APIView):
    def get(self, request, page, category):
        # 페이지당 3개의 게시물 보여주기
        category_name = category
        row_count = 3
        offset = (page - 1) * row_count
        limit = page * row_count

        category_condition = Q(category_name__contains=category_name)

        columns = [
            'wishlist_content',
            'member_name',
            'category_name',
            'created_date'
        ]

        category_wishlists = Wishlist.enabled_objects.filter(category_condition).annotate(member_name=F("member__member_nickname"),category_name=F("category__category_name")).values(*columns)

        return Response(category_wishlists[offset:limit])








