import math

from bootpay_backend import BootpayBackend
from django.db import transaction
from django.db.models import F, Q, Value, Count
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views import View
from rest_framework.response import Response
from rest_framework.views import APIView

from activity.models import ActivityReply, Activity, ActivityLike, ActivityMember
from activity.views import make_datetime
from alarm.models import Alarm
from club.models import ClubPostReply, ClubMember, Club, ClubNotice
from friend.models import Friend
from letter.models import Letter, ReceivedLetter, SentLetter
from member.models import Member, MemberFavoriteCategory, MemberProfile, MemberDeleteReason
from member.serializers import MemberSerializer
from notice.models import Notice
from pay.models import Pay, PayCancel
from teenplay_server.category import Category
from wishlist.models import WishlistReply, Wishlist


class MemberLoginWebView(View):
    def get(self, request):
        return render(request, 'member/web/login-web.html')


class MemberJoinWebView(View):
    def get(self, request):
        member_type = request.GET['type']
        member_email = request.GET['email']
        member_nickname = request.GET['name']
        context = {
            'member_type': member_type,
            'member_email': member_email,
            'member_nickname': member_nickname
        }
        return render(request, 'member/web/join-web.html', context=context)

    @transaction.atomic
    def post(self, request):
        data = request.POST
        marketing_agree = data.getlist('marketing_agree')
        marketing_agree = True if len(marketing_agree) else False
        privacy_agree = data.getlist('privacy_agree')
        privacy_agree = True if len(privacy_agree) else False

        data = {
            'member_email': data['member-email'],
            'member_nickname': data['member-name'],
            'member_marketing_agree': marketing_agree,
            'member_privacy_agree': privacy_agree,
            'member_type': data['member-type'],
            'member_phone': data['member-phone']
        }

        member = Member.objects.create(**data)
        member = MemberSerializer(member).data
        request.session['member'] = member
        return redirect('/')


from django.http import HttpResponse


class MypageInfoWebView(View):
    def get(self, request):
        # 개인의 정보를 나타내야 하기때문에 세션에 담아줍니다.
        member_id = request.session.get('member')
        if member_id is None:
            #  멤버정보가 없다는 뜻은 로그인을 안했다는 뜻으로 로그인부터 시켜줍니다.
            return redirect('member:login')
        #  정상적으로 로그인하고 접속했을땨의 공간입니다.
        else:
            # 들어올때는 세션이 반드시 필요합니다 마이페이지니까
            member = request.session.get('member')
            #  멤버의 사진, 카테고리는 별도로 저장이라 세션에 따로 담아줍니다.
            member_file = MemberProfile.objects.filter(member_id=member['id'])
            member_files = list(member_file.values('profile_path').filter(status=1))
            if len(member_files) != 0:
                request.session['member_files'] = member_files
            member_file = request.session.get('member_files')
            #  멤버의 사진, 카테고리는 별도로 저장이라 세션에 따로 담아줍니다.
            category_session = MemberFavoriteCategory.objects.filter(member_id=member['id'])
            category_session = list(category_session.values('status', 'category_id'))
            if len(category_session) != 0:
                request.session['member_category'] = category_session
            member_category = request.session.get('member_category')
            # 전체 카테고리 가져와서 뿌려줍니다.
            categories = Category.objects.all()
            # 이 전체내용 담아줍니다.
            return render(request, 'mypage/web/my-info-web.html',
                          {'member': member, 'categories': categories, 'member_files': member_file,
                           'member_category': member_category})

    @transaction.atomic
    def post(self, request):
        # 세션에서 member의 값을 가져옴
        member_data = request.session.get('member', 'member_files')
        #  화면에서 담은 사진을 가져옵니다.
        file = request.FILES

        if member_data:
            member_id = member_data['id']

            try:
                # member_id에 해당하는 Member 객체를 가져옴
                member = Member.objects.get(id=member_id)
            except Member.DoesNotExist:
                # 만약 member_id에 해당하는 Member 객체가 없을 경우 에러 처리
                return HttpResponse("Member matching query does not exist.", status=404)

            # 화면에 담은 내용을 가져옵니다.
            data = request.POST
            # 이름수정이 있다면 바꿔줍니다.
            if data.get('member-nickname') != '':
                member.member_nickname = data['member-nickname']
            # 전화번호 수정이 있다면 수정해줍니다.
            if data.get('member-phone') != '':
                member.member_phone = data['member-phone']
            # 성별은 필수 입력이라 바로 담아줍니다.
            member.member_gender = int(data['gender'])
            # 동의 여부를 확인해줍니다.
            if data.get('member-marketing_agree') == '1':
                member.member_marketing_agree = True
            else:
                member.member_marketing_agree = False
            if data.get('member-privacy_agree') == '1':
                member.member_privacy_agree = True
            else:
                member.member_privacy_agree = False
            # 생년원일 담아줍니다.
            if 'member-age' in data and data['member-age'] != '':
                member.member_birth = data['member-age']
            # 카테고리가 13개가있고 어떤것들을 선택했는지 담아줍니다.
            selected_categories = request.POST.getlist('selected_categories')

            # 기존의 회원 관심 카테고리 가져오기
            member_categories = MemberFavoriteCategory.objects.filter(member_id=member.id)


            for category_id in selected_categories:
                # 해당 카테고리가 이미 존재하는지 확인
                category_exists = member_categories.filter(category_id=category_id).exists()

                if category_exists:
                    # 이미 존재하면 status 변경
                    target_member_category = member_categories.filter(category_id=category_id).first()

                    if target_member_category:
                        # 특정 category_id에 대한 상태를 토글
                        target_member_category.status = 1 - target_member_category.status
                        target_member_category.save()
                else:
                    # 존재하지 않으면 새로운 레코드 생성
                    MemberFavoriteCategory.objects.create(member_id=member.id, category_id=category_id, status=1)
            # 사간 초기화 후 전체 저장
            member.updated_date = timezone.now()
            member.save(update_fields=['member_nickname', 'member_phone', 'member_gender', 'member_marketing_agree',
                                       'member_privacy_agree', 'member_birth', 'updated_date'])
            member_file = MemberProfile.objects.filter(member_id=member.id)
            for key, uploaded_file in file.items():
                try:
                    member_profile = MemberProfile.objects.get(member_id=member.id)
                    # 이미 프로필이 존재하는 경우 업데이트
                    member_profile.profile_path = uploaded_file
                    member_profile.save()
                except MemberProfile.DoesNotExist:
                    # 멤버 프로필이 없는 경우 생성
                    MemberProfile.objects.create(member_id=member.id, profile_path=uploaded_file, )

            # 수정된 데이터를 세션에 다시 저장
            request.session['member'] = {
                'id': member.id,
                'member_birth': member.member_birth,
                'member_email': member.member_email,
                'member_nickname': member.member_nickname,
                'member_address': member.member_address,
                'member_phone': member.member_phone,
                'member_gender': member.member_gender,
                'member_marketing_agree': member.member_marketing_agree,
                'member_privacy_agree': member.member_privacy_agree,
            }
            # 사진이 있다면 사진도 세션에 담아줍니다.
            member_files = list(member_file.values('profile_path').filter(status=1))
            if len(member_files) != 0:
                request.session['member_files'] = member_files
            # 카테고리도 세션에 담아줍니다.
            category_session = MemberFavoriteCategory.objects.filter(member_id=member.id)
            category_session = list(category_session.values('status', 'category_id'))
            if len(category_session) != 0:
                request.session['member_category'] = category_session

            return redirect('member:mypage-info')
        else:
            # 세션 데이터에서 member가 없는 경우 에러 처리
            return HttpResponse("Session data for member is missing.", status=400)


class MypageDeleteWebView(View):
    def get(self, request):
        # 멤버 정보랑 사진 들고갑니다 둘다 필요합니다.
        member = request.session['member']['id']
        frofile = MemberProfile.objects.filter(member_id=member)
        context = {'frofile': frofile

                   }
        return render(request, 'mypage/web/withdrawal-web.html', context)

    @transaction.atomic
    def post(self, request):
        #  일단 세션에서 멤버부터 불러오고
        member_data = request.session.get('member')
        # 삭제이유 케테고리, 이유를 받습니다
        text = request.POST.get("reason-text")
        number = request.POST.get("select_bum")
        # 데이터 분석을 위한 탈퇴이유를 받습니다.
        MemberDeleteReason.objects.create(delete_text=text, delete_reason=number)
        # 유저가 누구인지 확인하고 회원 탈퇴정보를 저장해줍니다.
        member_id = member_data['id']
        member = Member.objects.get(id=member_id)
        member.status = 0
        member.updated_date = timezone.now()
        member.save(update_fields=['status', 'updated_date'])
        # 세션에 담겨있는 정보를 날려줍니다.
        request.session.clear()
        return redirect('/')


class MypageLetterWebView(View):
    def get(self, request):
        # 필요 정보를 담아서 이동해줍니다.
        member = request.session.get('member')
        latest_letter = Letter.objects.latest('id')
        return render(request, 'mypage/web/my-letter-web.html', {"member": member, 'letter_id': latest_letter.id})


class MypageWriteAPIWebView(APIView):
    @transaction.atomic
    def post(self, request):
        # 담겨있는 데이터를 가져옵니다.(쪽지내용, 누구한테 보내는지)
        data = request.data
        # 이메일을 입력하면 ***(qwe123@asd.com)이런식으로 와서 일단 분리해줍니다 이메일만
        receiver_email = data['receiver_id'].split("(")[1][:-1]
        # 이메일 검사를 통해 누구인지 찾고
        receiver_instance = Member.objects.filter(member_email=receiver_email).first()
        #
        receiver_id = receiver_instance.id
        # Letter 모델 생성
        letter = Letter.objects.create(
            receiver_id=receiver_id,
            letter_content=data['letter_content'],
            sender_id=request.session['member']['id']
        )

        # ReceivedLetter 모델 생성
        ReceivedLetter.objects.create(letter_id=letter.id)

        # SentLetter 모델 생성
        SentLetter.objects.create(letter_id=letter.id)
        # 받은쪽지가 있다고 알람 보내주기
        Alarm.objects.create(target_id=letter.id, alarm_type=4, sender_id=letter.sender_id,
                             receiver_id=letter.receiver_id)

        return Response("good")


class MypageListAPIWebView(APIView):
    @transaction.atomic
    def get(self, request, member_id, page):
        # 각 쪽지별로 나타내는걸 구분하기 위해 데이터 사용(받은쪽지, 보낸쪽지)
        status_letter = request.GET.get('status_letter')
        # 한 페이지에 몇개의 데이터가 나오는지 나타내기
        row_count = 10
        # 페이지구분을 위해서 사용
        offset = (page - 1) * row_count
        limit = page * row_count

        # 전체 데이터 수를 세는 쿼리
        total_count = Letter.objects.filter(
            Q(sender_id=member_id, status=1) | Q(receiver_id=member_id, status=1)).count()

        # 전체 페이지 수 계산
        total_pages = (total_count + row_count - 1) // row_count

        # 페이지 범위에 해당하는 데이터 조회
        replies = Letter.objects.filter(Q(sender_id=member_id, status=1) | Q(receiver_id=member_id, status=1)) \
                      .values('letter_content', 'created_date', 'sender__member_nickname', 'receiver__member_nickname',
                              'id')[offset:limit]

        sender = Letter.objects.filter(sender_id=member_id, status=1) \
                     .values('letter_content', 'created_date', 'sender__member_nickname', 'receiver__member_nickname',
                             'id')[offset:limit]

        receiver = Letter.objects.filter(receiver_id=member_id, status=1) \
                       .values('letter_content', 'created_date', 'sender__member_nickname', 'receiver__member_nickname',
                               'id')[offset:limit]

        # 응답에 전체 페이지 수와 데이터 추가
        response_data = {
            'total_pages': total_pages,
            'replies': replies,

        }
        #  구분점에서 보낸사람만 찾기를 선택하면 관련정보만 분리해서 보내주기
        if status_letter == 'sender':
            response_data['replies'] = Letter.objects.filter(sender_id=member_id, status=1) \
                                           .values('letter_content', 'created_date', 'sender__member_nickname',
                                                   'receiver__member_nickname',
                                                   'id')[offset:limit]

            response_data['total_pages'] = (Letter.objects.filter(sender_id=member_id,
                                                                  status=1).count() + row_count - 1) // row_count
        #  구분점에서 보낸사람만 찾기를 선택하면 관련정보만 분리해서 보내주기
        elif status_letter == 'receiver':
            response_data['replies'] = Letter.objects.filter(receiver_id=member_id, status=1) \
                                           .values('letter_content', 'created_date', 'sender__member_nickname',
                                                   'receiver__member_nickname',
                                                   'id')[offset:limit]
            response_data['total_pages'] = (Letter.objects.filter(receiver_id=member_id,
                                                                  status=1).count() + row_count - 1) // row_count
        #  구분점에서 보낸사람만 찾기를 선택하면 관련정보만 분리해서 보내주기
        else:
            response_data['replies'] = Letter.objects.filter(
                Q(sender_id=member_id, status=1) | Q(receiver_id=member_id, status=1)) \
                                           .values('letter_content', 'created_date', 'sender__member_nickname',
                                                   'receiver__member_nickname', 'id')[offset:limit]

            response_data['total_pages'] = (Letter.objects.filter(
                Q(sender_id=member_id, status=1) | Q(receiver_id=member_id,
                                                     status=1)).count() + row_count - 1) // row_count

        return Response(response_data)


class MypageDeleteAPIWebView(APIView):
    @transaction.atomic
    def delete(self, request, letter_id):
        # 쪽지를 삭제한다면 그 쪽지 번호 받아서 지워줍니다.
        letter = Letter.objects.filter(id=letter_id)
        letter.update(status=0,updated_date=timezone.now())
        #  관련된 쪽지 모두 제거
        SentLetter.objects.filter(letter_id=letter_id).update(status=0, updated_date=timezone.now())
        ReceivedLetter.objects.filter(letter_id=letter_id).update(status=0, updated_date=timezone.now())

        return Response('good')

    @transaction.atomic
    def patch(self, request, letter_id):
        # 쪽지를 열람했다면 읽었다는 상태로 변환
        ReceivedLetter.objects.filter(letter_id=letter_id).update(is_read=0,updated_date=timezone.now())

        return Response('good')


class MypageCheckAPIWebViewMa(APIView):
    @transaction.atomic
    def post(self, request):
        member_email = request.data.get('member_email')
        # 이메일 받아오고 데이터에 있는지 없는지 확인
        member = Member.enabled_objects.filter(member_email=member_email)
        if member.exists():
            member = member.first()
            # 있으면 데이터들 보내줍니다.
            data = {
                'message': f'{member.member_nickname} ({member.member_email})'
            }
        else:
            # 없으면 경고문을 보내줍니다.
            data = {
                'message': '존재하지 않는 이메일입니다.'
            }

        return Response(data)


class MypageAlramView(View):
    @transaction.atomic
    def get(self, request):
        # 단순 페이지 이동
        return render(request, 'mypage/web/my-signal-web.html')


class MypageAlramAPIView(APIView):
    @transaction.atomic
    def get(self, request, member_id, page):
        # 페이지에 나타내는 데이터 숫자 선택
        row_count = 5
        # 데이터가 페이지별로 몇번부터 몇번 데이터까지인지 나타내준다.
        offset = (page - 1) * row_count
        limit = page * row_count
        # 알람데이터 보내주기
        alram = Alarm.objects.filter(receiver_id=member_id, status=1,is_read=1).values('id', 'alarm_type', 'target_id','created_date', 'receiver_id').order_by('-created_date')[offset:limit]

        return Response(alram)


class MypageAlramDeleteAPIView(APIView):
    @transaction.atomic
    def delete(self, request, alram_id):
        # 알람 읽음을 하면 데이터 변경해주기
        Alarm.objects.filter(id=alram_id).update(is_read=0,updated_date=timezone.now())

        return Response('good')


class MypageTeenchinview(View):
    def get(self, request):
        #  단순 페이지 이동
        return render(request, 'mypage/web/my-teenchin-web.html')


class MypageTeenchinAPIview(APIView):
    def get(self, request, member_id, page):
        # 페이지에 나타내는 데이터 숫자 선택
        row_count = 2
        # 데이터가 페이지별로 몇번부터 몇번 데이터까지인지 나타내준다.
        offset = (page - 1) * row_count
        limit = page * row_count

        teenchin = Friend.objects.filter(receiver_id=member_id).values('id', 'is_friend')[offset:limit]

        return Response(teenchin)


class MemberAlarmCountAPI(APIView):
    def get(self, request):
        member_id = request.GET.get('member-id')
        alarm_count = Alarm.enabled_objects.filter(receiver_id=member_id).count()

        return Response(alarm_count)


class MypageTeenchinAPIview(APIView):
    def get(self, request, member_id, page):
        # 검색, 필터기능 구현을 위한 데이터 받아오기
        status_letter = request.GET.get('status_teenchin')
        search_text = request.GET.get('search')[:-1]
        # 페이지에 나타내는 데이터 숫자 선택
        row_count = 9
        # 데이터가 페이지별로 몇번부터 몇번 데이터까지인지 나타내준다.
        offset = (page - 1) * row_count
        limit = page * row_count

        # 중복을 막기위해 조건별로 구분 후 담아줍니다.
        teenchin = []
        teenchin += Friend.objects.filter(sender_id=member_id, is_friend=1 ).values('id', 'is_friend', 'sender_id', 'receiver_id', 'sender__member_nickname',
                               'receiver__member_nickname','receiver__memberprofile__profile_path',)


        teenchin += Friend.objects.filter(receiver_id=member_id, is_friend=1 ).values('id', 'is_friend', 'sender_id', 'receiver_id', 'sender__member_nickname',
                               'receiver__member_nickname','sender__memberprofile__profile_path')
        teenchin += Friend.objects.filter(sender_id=member_id, is_friend=-1).values('id', 'is_friend', 'sender_id',
                                                                                   'receiver_id',
                                                                                   'sender__member_nickname',
                                                                                   'receiver__member_nickname',
                                                                                   'receiver__memberprofile__profile_path')




        teenchin += Friend.objects.filter(receiver_id=member_id, is_friend=-1).values('id', 'is_friend', 'sender_id',
                                                                                   'receiver_id',
                                                                                   'sender__member_nickname',
                                                                                   'receiver__member_nickname',
                                                                                   'sender__memberprofile__profile_path')

        # 필터를 통해 특정 상태의 틴친만 보여줍니다.
        if status_letter == 'case-a/':
            teenchin = []
            teenchin += Friend.objects.filter(sender_id=member_id, is_friend=1).values('id', 'is_friend', 'sender_id',
                                                                                       'receiver_id',
                                                                                       'sender__member_nickname',
                                                                                       'receiver__member_nickname',
                                                                                       'receiver__memberprofile__profile_path', )

            # 각각의 틴친의 활동 가입수를 보여줍니다
            for aactivity_count in teenchin:
                receiver_id = aactivity_count.get('receiver_id')
                manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                member_id=receiver_id).values().count()
                aactivity_count['aactivity_count'] = manager_favorite_categories_add
            # 각각의 틴친의 모임 가입수를 보여줍니다.
            for club_count in teenchin:
                receiver_id = club_count.get('receiver_id')
                manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                            member_id=receiver_id).values().count()
                club_count['club_count'] = manager_favorite_categories_add



            teenchin += Friend.objects.filter(receiver_id=member_id, is_friend=1).values('id', 'is_friend', 'sender_id',
                                                                                         'receiver_id',
                                                                                         'sender__member_nickname',
                                                                                         'receiver__member_nickname',
                                                                                         'sender__memberprofile__profile_path')
            # 검색을 한다면 그 검색내용을 걸러서 보여줍니다. (이메일, 이름 모두가능)
            if search_text:
                teenchin = []
                teenchin += Friend.objects.filter(sender_id=member_id, is_friend=1, receiver__member_nickname__icontains=search_text).values('id', 'is_friend',
                                                                                           'sender_id',
                                                                                           'receiver_id',
                                                                                           'sender__member_nickname',
                                                                                           'receiver__member_nickname',
                                                                                           'receiver__memberprofile__profile_path', )

                # 각각의 틴친의 활동 가입수를 보여줍니다
                for aactivity_count in teenchin:
                    receiver_id = aactivity_count.get('receiver_id')
                    manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                    member_id=receiver_id).values().count()
                    aactivity_count['aactivity_count'] = manager_favorite_categories_add
                # 각각의 틴친의 모임 가입수를 보여줍니다.
                for club_count in teenchin:
                    receiver_id = club_count.get('receiver_id')
                    manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                                member_id=receiver_id).values().count()
                    club_count['club_count'] = manager_favorite_categories_add




                teenchin += Friend.objects.filter(sender_id=member_id, is_friend=1, receiver__member_email__icontains=search_text).values('id', 'is_friend',
                                                                                           'sender_id',
                                                                                           'receiver_id',
                                                                                           'sender__member_nickname',
                                                                                           'receiver__member_nickname',
                                                                                           'receiver__memberprofile__profile_path', )
                # 각각의 틴친의 활동 가입수를 보여줍니다
                for aactivity_count in teenchin:
                    receiver_id = aactivity_count.get('receiver_id')
                    manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                    member_id=receiver_id).values().count()
                    aactivity_count['aactivity_count'] = manager_favorite_categories_add
                # 각각의 틴친의 모임 가입수를 보여줍니다.
                for club_count in teenchin:
                    receiver_id = club_count.get('receiver_id')
                    manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                                member_id=receiver_id).values().count()
                    club_count['club_count'] = manager_favorite_categories_add




                teenchin += Friend.objects.filter(receiver_id=member_id, is_friend=1,sender__member_email__icontains=search_text).values('id', 'is_friend',
                                                                                             'sender_id',
                                                                                             'receiver_id',
                                                                                             'sender__member_nickname',
                                                                                             'receiver__member_nickname',
                                                                                             'sender__memberprofile__profile_path')
                teenchin += Friend.objects.filter(receiver_id=member_id, is_friend=1,sender__member_nickname__icontains=search_text).values('id', 'is_friend',
                                                                                             'sender_id',
                                                                                             'receiver_id',
                                                                                             'sender__member_nickname',
                                                                                             'receiver__member_nickname',
                                                                                             'sender__memberprofile__profile_path')

        # 필터를 통해 특정 상태의 틴친만 보여줍니다.
        elif status_letter == 'case-b/':
            teenchin = []
            teenchin += Friend.objects.filter(sender_id=member_id, is_friend=-1).values('id', 'is_friend', 'sender_id',
                                                                                        'receiver_id',
                                                                                        'sender__member_nickname',
                                                                                        'receiver__member_nickname',
                                                                                        'receiver__memberprofile__profile_path')
            # 각각의 틴친의 활동 가입수를 보여줍니다
            for aactivity_count in teenchin:
                receiver_id = aactivity_count.get('receiver_id')
                manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                member_id=receiver_id).values().count()
                aactivity_count['aactivity_count'] = manager_favorite_categories_add
            # 각각의 틴친의 모임 가입수를 보여줍니다.
            for club_count in teenchin:
                receiver_id = club_count.get('receiver_id')
                manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                            member_id=receiver_id).values().count()
                club_count['club_count'] = manager_favorite_categories_add

            # 검색을 한다면 그 검색내용을 걸러서 보여줍니다. (이메일, 이름 모두가능)
            if search_text:
                teenchin = []
                teenchin += Friend.objects.filter(sender_id=member_id, is_friend=-1,receiver__member_nickname__icontains=search_text).values('id', 'is_friend',
                                                                                            'sender_id',
                                                                                            'receiver_id',
                                                                                            'sender__member_nickname',
                                                                                            'receiver__member_nickname',
                                                                                            'receiver__memberprofile__profile_path')
                # 각각의 틴친의 활동 가입수를 보여줍니다
                for aactivity_count in teenchin:
                    receiver_id = aactivity_count.get('receiver_id')
                    manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                    member_id=receiver_id).values().count()
                    aactivity_count['aactivity_count'] = manager_favorite_categories_add
                # 각각의 틴친의 모임 가입수를 보여줍니다.
                for club_count in teenchin:
                    receiver_id = club_count.get('receiver_id')
                    manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                                member_id=receiver_id).values().count()
                    club_count['club_count'] = manager_favorite_categories_add





                teenchin += Friend.objects.filter(sender_id=member_id, is_friend=-1,receiver__member_email__icontains=search_text).values('id', 'is_friend',
                                                                                            'sender_id',
                                                                                            'receiver_id',
                                                                                            'sender__member_nickname',
                                                                                            'receiver__member_nickname',
                                                                                            'receiver__memberprofile__profile_path')
                # 각각의 틴친의 활동 가입수를 보여줍니다
                for aactivity_count in teenchin:
                    receiver_id = aactivity_count.get('receiver_id')
                    manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                    member_id=receiver_id).values().count()
                    aactivity_count['aactivity_count'] = manager_favorite_categories_add
                # 각각의 틴친의 모임 가입수를 보여줍니다.
                for club_count in teenchin:
                    receiver_id = club_count.get('receiver_id')
                    manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                                member_id=receiver_id).values().count()
                    club_count['club_count'] = manager_favorite_categories_add




        # 필터를 통해 특정 상태의 틴친만 보여줍니다.
        elif status_letter == 'case-c/':
            teenchin = []
            teenchin += Friend.objects.filter(receiver_id=member_id, is_friend=-1).values('id', 'is_friend',
                                                                                          'sender_id',
                                                                                          'receiver_id',
                                                                                          'sender__member_nickname',
                                                                                          'receiver__member_nickname',
                                                                                          'sender__memberprofile__profile_path')
            # 각각의 틴친의 활동 가입수를 보여줍니다
            for aactivity_count in teenchin:
                sender_id = aactivity_count.get('sender_id')
                manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                member_id=sender_id).values().count()
                aactivity_count['aactivity_countss'] = manager_favorite_categories_add
            # 각각의 틴친의 모임 가입수를 보여줍니다.
            for club_count in teenchin:
                sender_id = club_count.get('sender_id')
                manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                            member_id=sender_id).values().count()
                club_count['club_countss'] = manager_favorite_categories_add

            # 검색을 한다면 그 검색내용을 걸러서 보여줍니다. (이메일, 이름 모두가능)
            if search_text:
                teenchin = []
                teenchin += Friend.objects.filter(receiver_id=member_id, is_friend=-1,sender__member_email__icontains=search_text).values('id', 'is_friend',
                                                                                              'sender_id',
                                                                                              'receiver_id',
                                                                                              'sender__member_nickname',
                                                                                              'receiver__member_nickname',
                                                                                              'sender__memberprofile__profile_path')
                # 각각의 틴친의 활동 가입수를 보여줍니다
                for aactivity_count in teenchin:
                    sender_id = aactivity_count.get('sender_id')
                    manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                    member_id=sender_id).values().count()
                    aactivity_count['aactivity_countss'] = manager_favorite_categories_add
                # 각각의 틴친의 모임 가입수를 보여줍니다.
                for club_count in teenchin:
                    sender_id = club_count.get('sender_id')
                    manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                                member_id=sender_id).values().count()
                    club_count['club_countss'] = manager_favorite_categories_add


                teenchin += Friend.objects.filter(receiver_id=member_id, is_friend=-1 ,sender__member_nickname__icontains=search_text).values('id', 'is_friend',
                                                                                              'sender_id',
                                                                                              'receiver_id',
                                                                                              'sender__member_nickname',
                                                                                              'receiver__member_nickname',
                                                                                              'sender__memberprofile__profile_path')
                # 각각의 틴친의 활동 가입수를 보여줍니다
                for aactivity_count in teenchin:
                    sender_id = aactivity_count.get('sender_id')
                    manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                    member_id=sender_id).values().count()
                    aactivity_count['aactivity_countss'] = manager_favorite_categories_add
                # 각각의 틴친의 모임 가입수를 보여줍니다.
                for club_count in teenchin:
                    sender_id = club_count.get('sender_id')
                    manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                                member_id=sender_id).values().count()
                    club_count['club_countss'] = manager_favorite_categories_add



        else:
            teenchin = []
            teenchin += Friend.objects.filter(sender_id=member_id, is_friend=1).values('id', 'is_friend', 'sender_id',
                                                                                       'receiver_id',
                                                                                       'sender__member_nickname',
                                                                                       'receiver__member_nickname',
                                                                                       'receiver__memberprofile__profile_path', )
            # 각각의 틴친의 활동 가입수를 보여줍니다
            for aactivity_count in teenchin:
                receiver_id = aactivity_count.get('receiver_id')
                manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                member_id=receiver_id).values().count()
                aactivity_count['aactivity_count'] = manager_favorite_categories_add
            # 각각의 틴친의 모임 가입수를 보여줍니다.
            for club_count in teenchin:
                receiver_id = club_count.get('receiver_id')
                manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                            member_id=receiver_id).values().count()
                club_count['club_count'] = manager_favorite_categories_add



            teenchin += Friend.objects.filter(receiver_id=member_id, is_friend=1).values('id', 'is_friend', 'sender_id',
                                                                                         'receiver_id',
                                                                                         'sender__member_nickname',
                                                                                         'receiver__member_nickname',
                                                                                         'sender__memberprofile__profile_path')
            # 각각의 틴친의 활동 가입수를 보여줍니다
            for aactivity_count in teenchin:
                sender_id = aactivity_count.get('sender_id')
                manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                member_id=sender_id).values().count()
                aactivity_count['aactivity_countss'] = manager_favorite_categories_add
            # 각각의 틴친의 모임 가입수를 보여줍니다.
            for club_count in teenchin:
                sender_id = club_count.get('sender_id')
                manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                            member_id=sender_id).values().count()
                club_count['club_countss'] = manager_favorite_categories_add


            teenchin += Friend.objects.filter(sender_id=member_id, is_friend=-1).values('id', 'is_friend', 'sender_id',
                                                                                        'receiver_id',
                                                                                        'sender__member_nickname',
                                                                                        'receiver__member_nickname',
                                                                                        'receiver__memberprofile__profile_path')
            # 각각의 틴친의 활동 가입수를 보여줍니다
            for aactivity_count in teenchin:
                receiver_id = aactivity_count.get('receiver_id')
                manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                member_id=receiver_id).values().count()
                aactivity_count['aactivity_count'] = manager_favorite_categories_add
            # 각각의 틴친의 모임 가입수를 보여줍니다.
            for club_count in teenchin:
                receiver_id = club_count.get('receiver_id')
                manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                            member_id=receiver_id).values().count()
                club_count['club_count'] = manager_favorite_categories_add



            teenchin += Friend.objects.filter(receiver_id=member_id, is_friend=-1).values('id', 'is_friend',
                                                                                          'sender_id',
                                                                                          'receiver_id',
                                                                                          'sender__member_nickname',
                                                                                          'receiver__member_nickname',
                                                                                          'sender__memberprofile__profile_path')

            # 각각의 틴친의 활동 가입수를 보여줍니다
            for aactivity_count in teenchin:
                sender_id = aactivity_count.get('sender_id')
                manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                member_id=sender_id).values().count()
                aactivity_count['aactivity_countss'] = manager_favorite_categories_add
            # 각각의 틴친의 모임 가입수를 보여줍니다.
            for club_count in teenchin:
                sender_id = club_count.get('sender_id')
                manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                            member_id=sender_id).values().count()
                club_count['club_countss'] = manager_favorite_categories_add
            # 검색을 한다면 그 검색내용을 걸러서 보여줍니다. (이메일, 이름 모두가능)
            if search_text:
                teenchin = []
                teenchin += Friend.objects.filter(sender_id=member_id, is_friend=1,receiver__member_nickname__icontains=search_text).values('id', 'is_friend',
                                                                                           'sender_id',
                                                                                           'receiver_id',
                                                                                           'sender__member_nickname',
                                                                                           'receiver__member_nickname',
                                                                                           'receiver__memberprofile__profile_path', )
                # 각각의 틴친의 활동 가입수를 보여줍니다
                for aactivity_count in teenchin:
                    receiver_id = aactivity_count.get('receiver_id')
                    manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                    member_id=receiver_id).values().count()
                    aactivity_count['aactivity_count'] = manager_favorite_categories_add
                # 각각의 틴친의 모임 가입수를 보여줍니다.
                for club_count in teenchin:
                    receiver_id = club_count.get('receiver_id')
                    manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                                member_id=receiver_id).values().count()
                    club_count['club_count'] = manager_favorite_categories_add




                teenchin += Friend.objects.filter(receiver_id=member_id, is_friend=1 ,sender__member_nickname__icontains=search_text).values('id', 'is_friend',
                                                                                             'sender_id',
                                                                                             'receiver_id',
                                                                                             'sender__member_nickname',
                                                                                             'receiver__member_nickname',
                                                                                             'sender__memberprofile__profile_path')
                # 각각의 틴친의 활동 가입수를 보여줍니다
                for aactivity_count in teenchin:
                    sender_id = aactivity_count.get('sender_id')
                    manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                    member_id=sender_id).values().count()
                    aactivity_count['aactivity_countss'] = manager_favorite_categories_add
                # 각각의 틴친의 모임 가입수를 보여줍니다.
                for club_count in teenchin:
                    sender_id = club_count.get('sender_id')
                    manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                                member_id=sender_id).values().count()
                    club_count['club_countss'] = manager_favorite_categories_add


                teenchin += Friend.objects.filter(sender_id=member_id, is_friend=-1,receiver__member_nickname__icontains=search_text).values('id', 'is_friend',
                                                                                            'sender_id',
                                                                                            'receiver_id',
                                                                                            'sender__member_nickname',
                                                                                            'receiver__member_nickname',
                                                                                            'receiver__memberprofile__profile_path')
                # 각각의 틴친의 활동 가입수를 보여줍니다
                for aactivity_count in teenchin:
                    receiver_id = aactivity_count.get('receiver_id')
                    manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                    member_id=receiver_id).values().count()
                    aactivity_count['aactivity_count'] = manager_favorite_categories_add
                # 각각의 틴친의 모임 가입수를 보여줍니다.
                for club_count in teenchin:
                    receiver_id = club_count.get('receiver_id')
                    manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                                member_id=receiver_id).values().count()
                    club_count['club_count'] = manager_favorite_categories_add



                teenchin += Friend.objects.filter(receiver_id=member_id, is_friend=-1,sender__member_nickname__icontains=search_text).values('id', 'is_friend',
                                                                                              'sender_id',
                                                                                              'receiver_id',
                                                                                              'sender__member_nickname',
                                                                                              'receiver__member_nickname',
                                                                                              'sender__memberprofile__profile_path')
                # 각각의 틴친의 활동 가입수를 보여줍니다
                for aactivity_count in teenchin:
                    sender_id = aactivity_count.get('sender_id')
                    manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                    member_id=sender_id).values().count()
                    aactivity_count['aactivity_countss'] = manager_favorite_categories_add
                # 각각의 틴친의 모임 가입수를 보여줍니다.
                for club_count in teenchin:
                    sender_id = club_count.get('sender_id')
                    manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                                member_id=sender_id).values().count()
                    club_count['club_countss'] = manager_favorite_categories_add


                teenchin += Friend.objects.filter(sender_id=member_id, is_friend=1,receiver__member_email__icontains=search_text).values('id', 'is_friend',
                                                                                           'sender_id',
                                                                                           'receiver_id',
                                                                                           'sender__member_nickname',
                                                                                           'receiver__member_nickname',
                                                                                           'receiver__memberprofile__profile_path', )
                # 각각의 틴친의 활동 가입수를 보여줍니다
                for aactivity_count in teenchin:
                    receiver_id = aactivity_count.get('receiver_id')
                    manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                    member_id=receiver_id).values().count()
                    aactivity_count['aactivity_count'] = manager_favorite_categories_add
                # 각각의 틴친의 모임 가입수를 보여줍니다.
                for club_count in teenchin:
                    receiver_id = club_count.get('receiver_id')
                    manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                                member_id=receiver_id).values().count()
                    club_count['club_count'] = manager_favorite_categories_add


                teenchin += Friend.objects.filter(receiver_id=member_id, is_friend=1,sender__member_email__icontains=search_text).values('id', 'is_friend',
                                                                                             'sender_id',
                                                                                             'receiver_id',
                                                                                             'sender__member_nickname',
                                                                                             'receiver__member_nickname',
                                                                                             'sender__memberprofile__profile_path')
                # 각각의 틴친의 활동 가입수를 보여줍니다
                for aactivity_count in teenchin:
                    sender_id = aactivity_count.get('sender_id')
                    manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                    member_id=sender_id).values().count()
                    aactivity_count['aactivity_countss'] = manager_favorite_categories_add
                # 각각의 틴친의 모임 가입수를 보여줍니다.
                for club_count in teenchin:
                    sender_id = club_count.get('sender_id')
                    manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                                member_id=sender_id).values().count()
                    club_count['club_countss'] = manager_favorite_categories_add


                teenchin += Friend.objects.filter(sender_id=member_id, is_friend=-1,receiver__member_email__icontains=search_text).values('id', 'is_friend',
                                                                                            'sender_id',
                                                                                            'receiver_id',
                                                                                            'sender__member_nickname',
                                                                                            'receiver__member_nickname',
                                                                                            'receiver__memberprofile__profile_path')
                # 각각의 틴친의 활동 가입수를 보여줍니다
                for aactivity_count in teenchin:
                    receiver_id = aactivity_count.get('receiver_id')
                    manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                    member_id=receiver_id).values().count()
                    aactivity_count['aactivity_count'] = manager_favorite_categories_add
                # 각각의 틴친의 모임 가입수를 보여줍니다.
                for club_count in teenchin:
                    receiver_id = club_count.get('receiver_id')
                    manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                                member_id=receiver_id).values().count()
                    club_count['club_count'] = manager_favorite_categories_add


                teenchin += Friend.objects.filter(receiver_id=member_id, is_friend=-1,sender__member_email__icontains=search_text).values('id', 'is_friend',
                                                                                              'sender_id',
                                                                                              'receiver_id',
                                                                                              'sender__member_nickname',
                                                                                              'receiver__member_nickname',
                                                                                              'sender__memberprofile__profile_path')
                # 각각의 틴친의 활동 가입수를 보여줍니다
                for aactivity_count in teenchin:
                    sender_id = aactivity_count.get('sender_id')
                    manager_favorite_categories_add = ActivityMember.objects.filter(status=1,
                                                                                    member_id=sender_id).values().count()
                    aactivity_count['aactivity_countss'] = manager_favorite_categories_add
                # 각각의 틴친의 모임 가입수를 보여줍니다.
                for club_count in teenchin:
                    sender_id = club_count.get('sender_id')
                    manager_favorite_categories_add = ClubMember.objects.filter(status=1,
                                                                                member_id=sender_id).values().count()
                    club_count['club_countss'] = manager_favorite_categories_add



        return Response(teenchin[offset:limit])


class MypageTeenchindeleteview(APIView):
    @transaction.atomic
    def delete(self, request, friend_id):
        # 친구 제거를 할때 자신이 보낸사람인지 받은사람인지 구분 후 제거작업을 합니다.
        if Friend.objects.filter(receiver_id=friend_id,sender_id=request.session['member']['id']):
            target_id = Friend.objects.filter(receiver_id=friend_id, sender_id=request.session['member']['id']).update(is_friend=0, updated_date=timezone.now())
            # 알람도 같이 보내줘야합니다.
            Alarm.objects.create(target_id=target_id, receiver_id=friend_id, alarm_type=15,
                                 sender_id=request.session['member']['id'])
        # 친구 제거를 할때 자신이 보낸사람인지 받은사람인지 구분 후 제거작업을 합니다.
        elif Friend.objects.filter(receiver_id=request.session['member']['id'],sender_id=friend_id):
            target_id = Friend.objects.filter(receiver_id=request.session['member']['id'], sender_id=friend_id).update(is_friend=0, updated_date=timezone.now())
            # 알람도 같이 보내줘야합니다.
            Alarm.objects.create(target_id=target_id, receiver_id=friend_id, alarm_type=15,
                                 sender_id=request.session['member']['id'])

        return Response('good')

    @transaction.atomic
    def patch(self, request, friend_id):
        # 친구 받는 작업을 할때 보낸사람, 받는사람 구분해서 작업해줍니다.
        if Friend.objects.filter(receiver_id=friend_id, sender_id=request.session['member']['id']):
            target_id = Friend.objects.filter(receiver_id=friend_id, sender_id=request.session['member']['id']).update(
                is_friend=1, updated_date=timezone.now())
            # 알람도 같이 보내줘야합니다.
            Alarm.objects.create(target_id=target_id, receiver_id=friend_id, alarm_type=14,
                                 sender_id=request.session['member']['id'])
        # 친구 받는 작업을 할때 보낸사람, 받는사람 구분해서 작업해줍니다.
        elif Friend.objects.filter(receiver_id=request.session['member']['id'], sender_id=friend_id):
            target_id = Friend.objects.filter(receiver_id=request.session['member']['id'], sender_id=friend_id).update(
                is_friend=1, updated_date=timezone.now())
            # 알람도 같이 보내줘야합니다.
            Alarm.objects.create(target_id=target_id, receiver_id=friend_id, alarm_type=14,
                                 sender_id=request.session['member']['id'])

        return Response('good')


class MypageTeenchinLetterAPIview(APIView):
    @transaction.atomic
    def post(self, request):
        data = request.data
        # 누구에게 보낼지 정해준다음
        receiver_id = data['receiver_id']
        # 받는사람에게 보내줍니다.
        letter = Letter.objects.create(
            receiver_id=receiver_id,
            letter_content=data['letter_content'],
            sender_id=request.session['member']['id']
        )
        ReceivedLetter.objects.create(letter_id=letter.id)

        # SentLetter 모델 생성
        SentLetter.objects.create(letter_id=letter.id)
        # 알람도 보내줍니다.
        Alarm.objects.create(target_id=letter.id, alarm_type=4, sender_id=letter.sender_id,
                             receiver_id=letter.receiver_id)

        return Response("good")


class MapagePaymentView(View):
    def get(self, request):
        # 페이지 이동
        return render(request, 'mypage/web/my-payment-web.html')


class MypagePayListAPIVIEW(APIView):

    def get(self, request, member_id, page):
        # 페이지에 나타내는 데이터 숫자 선택
        row_count = 3
        # 데이터가 페이지별로 몇번부터 몇번 데이터까지인지 나타내준다.
        offset = (page - 1) * row_count
        limit = page * row_count

        pay = Pay.objects.filter(member_id=member_id, status=1).values('id', 'created_date', 'activity__activity_title',
                                                                       'activity__club__club_name',
                                                                       'activity__activity_intro',
                                                                       'member__club__club_intro',
                                                                       'activity__activity_title',
                                                                       'activity__thumbnail_path',
                                                                       'activity__id',
                                                                       'activity__recruit_end')[offset:limit]




        return Response(pay)


class MypagePayDeleteAPIVIEW(APIView):
    @transaction.atomic
    def post(self, request):
        # 결제 취소시 데이터 분석을 위해 이유를 담아둡니다. / 결제금액은 현재 20.000고정이지만 바뀌면 바껴서 적용될수있게 받아줍니다.
        pay_reason = request.data
        reason = pay_reason['reason']
        pay_id = pay_reason['pay']
        # 취소하는 활동이 뭔지 확인
        activity = Activity.objects.filter(pay_id=pay_id).first()
        pay = Pay.objects.filter(id=pay_id).first()
        # 결제 테이블 상태 바꿔줍니다.
        pay.status = 0
        pay.updated_date=timezone.now()
        pay.save(update_fields=['status','updated_date'])
        #  활동도 정지해줍니다.
        activity.status = 0
        activity.updated_date=timezone.now()
        activity.save(update_fields=['status','updated_date'])
        # 결제에 맞는 영수증을 받은 후 그 영수증 번호를 취소해줍니다.
        receipt_id = pay.receipt_id
        # 부트페이를 사용하기 위해 아이디 암호키 받아줍니다,
        bootpay = BootpayBackend('65e44626e57a7e001be37370',
                                 'NQmDRBsgOfziMiNXUEKrJGQ+YhXZncneSVG/auKihFA=')
        # 토큰도 받아줍니다.
        token = bootpay.get_access_token()
        # 부트페이에서 요청한 대로 필요정보를 담아줘서 취소합니다.
        if 'error_code' not in token:
            bootpay.cancel_payment(receipt_id=receipt_id,
                                   cancel_price=pay.price,
                                   cancel_username='관리자', cancel_message='취소됨')


        PayCancel.objects.create(pay_cancel_reason=reason)
        return Response('good')



class MypageReplyView(View):
    def get(self, request):
        # 단순 페이지 이동
        return render(request, 'mypage/web/my-reply-web.html')


class MypageReplyAPIVIEW(APIView):
    def get(self, request, member_id, page):
        # 필터에 따라 결과값을 보여줍니다.
        status_reply = request.GET.get('status_reply')
        # 페이지에 나타내는 데이터 숫자 선택
        row_count = 10
        # 데이터가 페이지별로 몇번부터 몇번 데이터까지인지 나타내준다.
        offset = (page - 1) * row_count
        limit = page * row_count
        # 전체 데이터가 몇개인지 나타내고
        total_count = 0

        total_count += WishlistReply.objects.filter(member_id=member_id, status=1).count()
        total_count += ActivityReply.objects.filter(member_id=member_id, status=1).count()
        total_count += ClubPostReply.objects.filter(member_id=member_id, status=1).count()

        # 전체 페이지 수 계산
        total_pages = (total_count + row_count - 1) // row_count
        reply = []

        reply += WishlistReply.objects.filter(member_id=member_id, status=1).values('id', 'reply_content',
                                                                                    'created_date', 'wishlist_id',
                                                                                    'wishlist__wishlist_content')
        reply += ActivityReply.objects.filter(member_id=member_id, status=1).values('id', 'reply_content',
                                                                                    'created_date', 'activity_id',
                                                                                    'activity__activity_title')
        reply += ClubPostReply.objects.filter(member_id=member_id, status=1).values('id', 'reply_content',
                                                                                    'created_date', 'club_post_id',
                                                                                    'club_post__post_title')
        # 데이터를 lambda를 통해 내림차순으로 정렬
        reply.sort(key=lambda x: x['created_date'], reverse=True)
        # 데이터를 담아줍니다.
        response_data = {
            'total_pages': total_pages,
            'reply': reply[offset:limit],

        }
        # 위시리스트 데이터만 필요로 할때
        if status_reply == 'wish':
            # 데이터를 분리해서 받아줍니다.
            response_data['reply'] = WishlistReply.objects.filter(member_id=member_id, status=1).values('id',
                                                                                                        'reply_content',
                                                                                                        'created_date',
                                                                                                        'wishlist_id',
                                                                                                        'wishlist__wishlist_content')[
                                     offset:limit]
            # 데이터를 분리해서 받아줍니다.
            response_data['total_pages'] = (WishlistReply.objects.filter(member_id=member_id,
                                                                         status=1).count() + row_count - 1) // row_count

        # 홍보글 데이터만 필요할때
        elif status_reply == 'post':
            # 데이터를 분리해서 받아줍니다.
            response_data['reply'] = ClubPostReply.objects.filter(member_id=member_id, status=1).values('id',
                                                                                                        'reply_content',
                                                                                                        'created_date',
                                                                                                        'club_post_id',
                                                                                                        'club_post__post_title')[
                                     offset:limit]
            # 데이터를 분리해서 받아줍니다.
            response_data['total_pages'] = (ClubPostReply.objects.filter(member_id=member_id,
                                                                         status=1).count() + row_count - 1) // row_count
        # 활동 데이터만 필요로 할때
        elif status_reply == 'ac':
            # 데이터를 분리해서 받아줍니다.
            response_data['reply'] = ActivityReply.objects.filter(member_id=member_id, status=1).values('id',
                                                                                                        'reply_content',
                                                                                                        'created_date',
                                                                                                        'activity_id',
                                                                                                        'activity__activity_title')[
                                     offset:limit]
            # 데이터를 분리해서 받아줍니다.
            response_data['total_pages'] = (ActivityReply.objects.filter(member_id=member_id,
                                                                         status=1).count() + row_count - 1) // row_count

        else:

            total_count = 0

            total_count += WishlistReply.objects.filter(member_id=member_id, status=1).count()
            total_count += ActivityReply.objects.filter(member_id=member_id, status=1).count()
            total_count += ClubPostReply.objects.filter(member_id=member_id, status=1).count()

            # 전체 페이지 수 계산
            total_pages = (total_count + row_count - 1) // row_count

            reply = []

            reply += WishlistReply.objects.filter(member_id=member_id, status=1).values('id', 'reply_content',
                                                                                        'created_date', 'wishlist_id',
                                                                                        'wishlist__wishlist_content')
            reply += ActivityReply.objects.filter(member_id=member_id, status=1).values('id', 'reply_content',
                                                                                        'created_date', 'activity_id',
                                                                                        'activity__activity_title')
            reply += ClubPostReply.objects.filter(member_id=member_id, status=1).values('id', 'reply_content',
                                                                                        'created_date', 'club_post_id',
                                                                                        'club_post__post_title')
            reply.sort(key=lambda x: x['created_date'], reverse=True)
            response_data = {
                'total_pages': total_pages,
                'reply': reply[offset:limit],

            }

        return Response(response_data)


class MypageReplyDeleteAPIVIEW(APIView):
    @transaction.atomic
    def delete(self, request, reply_id):
        # 삭제 할때 받아오는 데이터 + 구분 알파벳을 사용해서 삭제
        if reply_id.startswith('a'):
            ActivityReply.objects.filter(id=int(reply_id[1:])).update(status=0,updated_date=timezone.now())
        elif reply_id.startswith('w'):
            WishlistReply.objects.filter(id=int(reply_id[1:])).update(status=0,updated_date=timezone.now())
        elif reply_id.startswith('p'):
            ClubPostReply.objects.filter(id=int(reply_id[1:])).update(status=0,updated_date=timezone.now())

        return Response('good')


class TeenChinAPI(APIView):
    def get(self, request):
        member_id = request.session.get('member').get('id')
        teenchin_id = request.GET.get('teenchin-id')
        send_friend = Friend.objects.filter(sender_id=member_id, receiver_id=teenchin_id)
        receive_friend = Friend.objects.filter(receiver_id=member_id, sender_id=teenchin_id)
        teenchin_status = 0
        is_sender = False
        if send_friend.exists():
            send_friend = send_friend.first()
            teenchin_status = send_friend.is_friend
            is_sender = True
        elif receive_friend.exists():
            receive_friend = receive_friend.first()
            teenchin_status = receive_friend.is_friend

        return Response({
            'teenchinStatus': teenchin_status,
            'isSender': is_sender,
        })

    def post(self, request):
        member_id = request.session.get('member').get('id')
        teenchin_id = request.data.get('teenchinId')

        # 혹시 이미 친구인데 넘어왔을 경우 바로 return
        send_friend = Friend.objects.filter(sender_id=member_id, receiver_id=teenchin_id, is_friend=1)
        if send_friend.exists():
            return Response("already exists")
        receive_friend = Friend.objects.filter(sender_id=teenchin_id, receiver_id=member_id, is_friend=1)
        if receive_friend.exists():
            return Response("already exists")

        # 먼저 상태가 0인 컬럼이 있는지 검사(sender와 receiver가 다르므로 두 번 해야한다)
        send_friend = Friend.objects.filter(sender_id=member_id, receiver_id=teenchin_id, is_friend=0)
        if send_friend.exists():
            send_friend = send_friend.first()
            send_friend.is_friend = -1
            send_friend.updated_date = timezone.now()
            send_friend.save(update_fields=['is_friend', 'updated_date'])
            # 알람 추가
            alarm_data = {
                'target_id': member_id,
                'alarm_type': 5,
                'sender_id': member_id,
                'receiver_id': teenchin_id
            }
            alarm, created = Alarm.objects.get_or_create(**alarm_data)
            if not created:
                alarm.status = 1
                alarm.updated_date = timezone.now()
                alarm.save(update_fields=['status', 'updated_date'])

            return Response("success")
        receive_friend = Friend.objects.filter(sender_id=teenchin_id, receiver_id=member_id, is_friend=0)
        if receive_friend.exists():
            receive_friend = receive_friend.first()
            receive_friend.sender_id = member_id
            receive_friend.receiver_id = teenchin_id
            receive_friend.is_friend = -1
            receive_friend.updated_date = timezone.now()
            receive_friend.save(update_fields=['is_friend', 'updated_date', 'sender_id', 'receiver_id'])
            # 알람 추가
            alarm_data = {
                'target_id': member_id,
                'alarm_type': 5,
                'sender_id': member_id,
                'receiver_id': teenchin_id
            }
            alarm, created = Alarm.objects.get_or_create(**alarm_data)
            if not created:
                alarm.status = 1
                alarm.updated_date = timezone.now()
                alarm.save(update_fields=['status', 'updated_date'])

            return Response("success")
        # 없다면 새로 생성
        Friend.objects.create(sender_id=member_id, receiver_id=teenchin_id)
        # 알람 추가
        alarm_data = {
            'target_id': member_id,
            'alarm_type': 5,
            'sender_id': member_id,
            'receiver_id': teenchin_id
        }
        alarm, created = Alarm.objects.get_or_create(**alarm_data)
        if not created:
            alarm.status = 1
            alarm.updated_date = timezone.now()
            alarm.save(update_fields=['status', 'updated_date'])

        return Response("success")

    def patch(self, request):
        member_id = request.session.get('member').get('id')
        teenchin_id = request.data.get('teenchinId')
        is_sender = request.data.get('isSender')
        is_accept = request.data.get('isAccept')

        # is_sender > True -> 신청 취소만 가능 (is_accept는 관계없음)
        # is_sender > False -> is_accept가 True면 수락, False면 거절

        # 혹시 이미 친구인데 넘어왔을 경우 바로 return
        send_friend = Friend.objects.filter(sender_id=member_id, receiver_id=teenchin_id, is_friend=1)
        if send_friend.exists():
            return Response("already exists")
        receive_friend = Friend.objects.filter(sender_id=teenchin_id, receiver_id=member_id, is_friend=1)
        if receive_friend.exists():
            return Response("already exists")

        # 내가 보냈을 경우 신청을 취소하는 로직
        if is_sender:
            send_friend = Friend.objects.filter(sender_id=member_id, receiver_id=teenchin_id, is_friend=-1)
            if send_friend.exists():
                send_friend = send_friend.first()
                send_friend.is_friend = 0
                send_friend.updated_date = timezone.now()
                send_friend.save(update_fields=['is_friend', 'updated_date'])
                # 신청할 때 떴던 알람의 status를 0으로 바꿔주자!
                alarm_data = {
                    'target_id': member_id,
                    'alarm_type': 5,
                    'sender_id': member_id,
                    'receiver_id': teenchin_id,
                }
                alarm = Alarm.objects.filter(**alarm_data)
                if alarm.exists():
                    alarm = alarm.first()
                    alarm.status = 0
                    alarm.updated_date = timezone.now()
                    alarm.save(update_fields=['status', 'updated_date'])

                return Response("success")

        # 다른 틴친으로부터 온 요청을 수락/거절할 때
        receive_friend = Friend.objects.filter(sender_id=teenchin_id, receiver_id=member_id, is_friend=-1)
        if receive_friend.exists():
            receive_friend = receive_friend.first()
            # 수락할 때
            if is_accept:
                receive_friend.is_friend = 1
                receive_friend.updated_date = timezone.now()
                receive_friend.save(update_fields=['is_friend', 'updated_date'])
                alarm_data = {
                    'target_id': teenchin_id,
                    'alarm_type': 14,
                    'sender_id': teenchin_id,
                    'receiver_id': member_id
                }
                alarm, created = Alarm.objects.get_or_create(**alarm_data)
                if not created:
                    alarm.status = 1
                    alarm.updated_date = timezone.now()
                    alarm.save(update_fields=['status', 'updated_date'])
                return Response("success")

            # 거절할 때
            receive_friend.is_friend = 0
            receive_friend.updated_date = timezone.now()
            receive_friend.save(update_fields=['is_friend', 'updated_date'])
            # 신청할 때 떴던 알람의 status를 0으로 바꿔주자!
            alarm_data = {
                'target_id': member_id,
                'alarm_type': 5,
                'sender_id': member_id,
                'receiver_id': teenchin_id,
            }
            alarm = Alarm.objects.filter(**alarm_data)
            if alarm.exists():
                alarm = alarm.first()
                alarm.status = 0
                alarm.updated_date = timezone.now()
                alarm.save(update_fields=['status', 'updated_date'])

            return Response("success")

        return Response("fail")

    def delete(self, request):
        member_id = request.session.get('member').get('id')
        teenchin_id = request.data.get('teenchinId')
        send_friend = Friend.objects.filter(sender_id=member_id, receiver_id=teenchin_id, is_friend=1)
        if send_friend.exists():
            send_friend = send_friend.first()
            send_friend.is_friend = 0
            send_friend.updated_date = timezone.now()
            send_friend.save(update_fields=['is_friend', 'updated_date'])
            # 거절 알림
            alarm_data = {
                'target_id': member_id,
                'alarm_type': 15,
                'sender_id': member_id,
                'receiver_id': teenchin_id
            }
            alarm, created = Alarm.objects.get_or_create(**alarm_data)
            if not created:
                alarm = alarm.first()
                alarm.status = 1
                alarm.updated_date = timezone.now()
                alarm.save(update_fields=['status', 'updated_date'])

            return Response("success")

        receive_friend = Friend.objects.filter(sender_id=teenchin_id, receiver_id=member_id, is_friend=1)
        if receive_friend.exists():
            receive_friend = receive_friend.first()
            receive_friend.is_friend = 0
            receive_friend.updated_date = timezone.now()
            receive_friend.save(update_fields=['is_friend', 'updated_date'])
            # 거절 알림
            alarm_data = {
                'target_id': member_id,
                'alarm_type': 15,
                'sender_id': member_id,
                'receiver_id': teenchin_id
            }
            alarm, created = Alarm.objects.get_or_create(**alarm_data)
            if not created:
                alarm = alarm.first()
                alarm.status = 1
                alarm.updated_date = timezone.now()
                alarm.save(update_fields=['status', 'updated_date'])

            return Response("success")

        return Response("fail")


class ClubAlarmManageAPI(APIView):
    def get(self, request):
        member_id = request.session.get('member').get('id')
        club_id = request.GET.get('club-id')
        club_member = ClubMember.enabled_objects.filter(member_id=member_id, club_id=club_id)
        if not club_member.exists():
            return Response("Not found")
        club_member = club_member.first()
        club_member.alarm_status = not club_member.alarm_status
        club_member.updated_date = timezone.now()
        club_member.save(update_fields=['alarm_status', 'updated_date'])

        return Response("success")


class MypageActivityListView(View):
    def get(self, request, club_id):
        order = request.GET.get('order', '최신순')
        page = request.GET.get('page', 1)
        page_info = {
            'order': order,
            'page': page
        }

        club_profile = Club.enabled_objects.filter(id=club_id).values('club_profile_path').first()
        club_name = Club.enabled_objects.filter(id=club_id).values('club_name').first()
        print(club_profile)
        club_member_count = ClubMember.enabled_objects.filter(club_id=club_id).count()

        club_notice_queryset = ClubNotice.objects.filter(club_id=club_id)
        club_notice_count = club_notice_queryset.count()
        # club_notices = club_notice_queryset.values('id', 'notice_title', 'notice_content', 'status')

        waiting_member_count = ClubMember.objects.filter(club_id=club_id, status=-1).count()

        activity_queryset = Activity.objects.filter(
            club_id=club_id,
            recruit_start__lt=timezone.now(),
            recruit_end__gt=timezone.now(),
            status=1
        )
        activity_count = activity_queryset.count()

        activity_end_queryset = Activity.objects.filter(club_id=club_id, activity_end__lt=timezone.now(), status=1)
        activity_end_count = activity_end_queryset.count()

        insite = {
            'club_member_count': club_member_count,
            'club_notice_count': club_notice_count,
            'activity_count': activity_count,
            'waiting_member_count': waiting_member_count,
            'activity_end_count': activity_end_count,
            'club_profile': club_profile.get('club_profile_path') if club_profile else '',
            'club_name': club_name.get('club_name')
        }
        print(insite)
        activities_queryset = Activity.enabled_objects.filter(club_id=club_id, activity_end__gt=timezone.now(),
                                                              status=1)
        activities_count = activities_queryset.count()

        notices = Notice.objects.filter(notice_type=0).values('id', 'notice_title', 'created_date')[:4]
        for notice in notices:
            notice['created_date'] = notice['created_date'].strftime("%Y.%m.%d")

        club_notices = ClubNotice.objects.filter(club_id=club_id, status=1).values('id', 'notice_title',
                                                                                   'created_date')[:4]
        for club_notice in club_notices:
            club_notice['created_date'] = club_notice['created_date'].strftime("%Y.%m.%d")

        context = {
            'insite': insite,
            'page_info': page_info,
            'activities_count': activities_count,
            'notices': notices,
            'club_notices': club_notices,
            'club_id': club_id
        }

        return render(request, 'mypage/web/management-club-web.html', context)

    def post(self, request):
        datas = request.POST

        context = {
            'page_info': {
                'order': datas.get('order', '최신순'),
                'page': datas.get('page', 1)
            }
        }

        return render(request, 'mypage/web/management-club-web.html', context)


class MypageActivityListAPI(APIView):
    def post(self, request, club_id):
        order = request.data.get('order', '최신 개설순')
        page = int(request.data.get('page', 1))

        row_count = 6
        offset = (page - 1) * row_count
        limit = page * row_count

        weekday_translation = {
            'Mon': '월',
            'Tue': '화',
            'Wed': '수',
            'Thu': '목',
            'Fri': '금',
            'Sat': '토',
            'Sun': '일'
        }
        sort_field = '-created_date'
        if order == '최신 개설순':
            sort_field = '-created_date'
        elif order == '활동 일시순':
            sort_field = '-activity_start'

        # 조회수 어딧느닞 모르겠음
        # elif order == '인기순':
        #     pass

        activities_queryset = Activity.enabled_objects.filter(club_id=club_id, activity_end__gt=timezone.now(),
                                                              status=1)

        total_count = activities_queryset.count()

        page_count = 5

        end_page = math.ceil(page / page_count) * page_count
        start_page = end_page - page_count + 1
        real_end = math.ceil(total_count / row_count)
        end_page = real_end if end_page > real_end else end_page

        if end_page == 0:
            end_page = 1

        page_info = {
            'totalCount': total_count,
            'startPage': start_page,
            'endPage': end_page,
            'page': page,
            'realEnd': real_end,
            'pageCount': page_count,
        }

        activities = list(activities_queryset.values('id', 'activity_title', 'activity_start', 'created_date').order_by(
            sort_field)[offset:limit])

        for activity in activities:
            activity_start = activity['activity_start']
            create_date = activity['created_date']
            activity['activity_start'] = activity_start.strftime("%m월 %d일") + '(' + weekday_translation[
                activity_start.strftime('%a')] + ')' + activity_start.strftime(" %H:%M")
            activity['created_date'] = create_date.strftime("%m월 %d일") + '(' + weekday_translation[
                create_date.strftime('%a')] + ')' + create_date.strftime(" %H:%M")

        activities.append(page_info)
        return Response(activities)


class MypageMyClubView(View):
    def get(self, request):
        order = request.GET.get('order', '이름 순')
        page = request.GET.get('page', 1)

        context = {
            'order':order,
            'page':page
        }
        return render(request, 'mypage/web/my-club-web.html', context)


class MypageMyClubAPI(APIView):
    def post(self, request):
        member = request.session.get('member')
        order = request.data.get('order', '이름 순')
        page = int(request.data.get('page', 1))
        print(page,order)

        filter = 'name'
        if order == '최신순':
            filter = '-created_date'
        if order == '오래된 순':
            filter ='created_date'
        elif order == '활동 순':
            filter = '-activity_count'


        row_count = 6
        offset = (page - 1) * row_count
        limit = page * row_count

        clubs = Club.enabled_objects.filter(member_id=member['id']) \
            .annotate(name=F('club_name'), profile_path=F('club_profile_path'), activity_count=Count('activity'),
                      alarms=F('clubmember__alarm_status'), join_status=Value(2)) \
            .values('id', 'name', 'profile_path', 'alarms', 'join_status', 'activity_count', 'created_date')

        club_member = ClubMember.objects.filter(member_id=member['id']) \
            .annotate(name=F('club__club_name'), profile_path=F('club__club_profile_path'),
                      activity_count=Count('club__activity'), alarms=F('alarm_status'),
                      join_status=F('status')) \
            .values('club_id', 'name', 'profile_path', 'alarms', 'join_status', 'activity_count', 'created_date')

        combined_data = club_member.union(clubs).order_by(filter)

        club_list = list(combined_data[offset:limit])
        for club in club_list:
            print(club)
        return Response(club_list)


class MypageMyClubAlarmStatusAPI(APIView):
    def post(self, request, club_id):
        member = request.session.get('member')
        club_member_queryset = ClubMember.enabled_objects.filter(member_id=member['id'], club_id=club_id)
        alarm_status = club_member_queryset.values('alarm_status').first()
        if alarm_status['alarm_status']:
            club_member_queryset.update(alarm_status=False)
        else:
            club_member_queryset.update(alarm_status=True)

        return Response('ok')


class MypageMemberView(View):
    def get(self, request, club_id):
        search = request.GET.get('search', '')
        order = request.GET.get('order', '전체 상태')
        page = request.GET.get('page', 1)

        context = {
            'search': search,
            'order': order,
            'page': page,
            'club_id': club_id,
        }
        return render(request, 'mypage/web/management-club-member-web.html', context)

    def post(self, request):
        datas = request.POST
        context = {
            'order': datas.get('order', '최신순'),
            'page': datas.get('page', 1),
            'search': datas.get('search', 1),
        }

        return render(request, 'mypage/web/management-club-member-web.html', context)


class MypageMemberListAPI(APIView):
    def post(self, request, club_id):
        search = request.data.get('search', '')
        order = request.data.get('order', '전체 상태')
        page = int(request.data.get('page', 1))
        row_count = 8
        offset = (page - 1) * row_count
        limit = page * row_count

        condition = Q(club_id=club_id)
        if search:
            condition &= Q(member__member_email__contains=search) | Q(member__member_nickname__contains=search)
        if order == '가입대기':
            condition &= Q(status=-1)
        elif order == '가입중':
            condition &= Q(status=1)

        club_members_queryset = ClubMember.objects.filter(condition).exclude(status=0)

        club_members = list(club_members_queryset.values('id', 'member__member_nickname', 'member__member_email',
                                                         'member__member_gender',
                                                         'member__member_address', 'member__created_date', 'status',
                                                         'member')[offset:limit])
        club_members_count = club_members_queryset.count()

        page_count = 5
        end_page = math.ceil(page / page_count) * page_count
        start_page = end_page - page_count + 1
        real_end = math.ceil(club_members_count / row_count)
        end_page = real_end if end_page > real_end else end_page

        if end_page == 0:
            end_page = 1

        page_info = {
            'totalCount': club_members_count,
            'startPage': start_page,
            'endPage': end_page,
            'page': page,
            'realEnd': real_end,
            'pageCount': page_count,
        }
        for club_member in club_members:
            club_member['member__created_date'] = club_member['member__created_date'].strftime("%Y-%m-%d")
            member_favorite_categories = MemberFavoriteCategory.objects.filter(member=club_member['member']).values(
                'category__category_name')
            club_member['member_favorite_categories'] = list(member_favorite_categories)
            club_member['category_count'] = len(club_member['member_favorite_categories']) - 1

            activities = ActivityMember.objects.filter(member=club_member['member']).values('activity__activity_title')
            club_member['activities'] = list(activities)

        club_members.append(page_info)

        return Response(club_members)


class MypageClubDeleteView(View):
    def get(self, request, club_id):
        club = Club.objects.get(id=club_id)
        activities_count = Activity.enabled_objects.filter(club=club).count()
        club_members_count = ClubMember.objects.filter(club=club, status=-1).count()

        context = {
            'club_id': club_id,
            'club_name': club.club_name,
            'activities_count': activities_count,
            'club_members_count': club_members_count,
        }
        return render(request, 'mypage/web/management-club-delete-web.html', context)

    def post(self, request, club_id):
        club = Club.objects.get(id=club_id)
        club.status = False
        club.save()

        return redirect('/member/mypage-my-club/')


class MypageMemberStatusAPI(APIView):
    def delete(self, request, club_id):
        member = request.data.get('member_id')
        ClubMember.objects.filter(club_id=club_id, id=member).update(status=0)

        return Response('ok')

    def patch(self, request, club_id):
        member = request.data.get('member_id')
        ClubMember.objects.filter(club_id=club_id, id=member).update(status=1)

        return Response('ok')


class MypageNoticeView(View):
    def get(self, request, club_id):
        page = request.GET.get('page', 1)

        context = {
            'page': page,
            'club_id': club_id
        }

        return render(request, 'mypage/web/management-club-notice-web.html', context)


class MypageNoticeAPI(APIView):
    def post(self, request, club_id):
        del_item = request.data.get('del_item', '')
        page = int(request.data.get('page', 1))
        row_count = 5
        offset = (page - 1) * row_count
        limit = page * row_count

        if del_item:
            for item in del_item:
                ClubNotice.objects.filter(id=item, club_id=club_id, status=1).update(status=0)

        club_notices_queryset = ClubNotice.objects.filter(club_id=club_id, status=1)
        club_notices = list(club_notices_queryset.order_by('-id').values('id', 'notice_title', 'notice_content', 'created_date')[offset:limit])
        club_notices_count = club_notices_queryset.count()

        page_count = 5
        end_page = math.ceil(page / page_count) * page_count
        start_page = end_page - page_count + 1
        real_end = math.ceil(club_notices_count / row_count)
        end_page = real_end if end_page > real_end else end_page

        if end_page == 0:
            end_page = 1

        page_info = {
            'totalCount': club_notices_count,
            'startPage': start_page,
            'endPage': end_page,
            'page': page,
            'realEnd': real_end,
            'pageCount': page_count,
        }

        for club_notice in club_notices:
            club_notice['created_date'] = club_notice['created_date'].strftime("%Y.%m.%d")

        club_notices.append(page_info)

        return Response(club_notices)


class MypageNoticeDeleteAPI(APIView):
    def delete(self, request, club_id):
        del_list = request.data['del_list']
        for del_item in del_list:
            ClubNotice.objects.filter(id=del_item, club_id=club_id, status=1).update(status=0)

        return Response('ok')


class MypageNoticeCreateView(View):
    def get(self, request, club_id):
        context = {'club_id': club_id}
        return render(request, 'mypage/web/management-club-notice-write-web.html', context)

    def post(self, request, club_id):
        title = request.POST.get('title')
        content = request.POST.get('content')
        club = Club.enabled_objects.get(id=club_id)

        data = {
            'club': club,
            'notice_title': title,
            'notice_content': content
        }

        ClubNotice.objects.create(**data)
        # 상세페이지 주소로 이동하게 해야함
        return redirect(f'/member/mypage-notice/{club_id}/')


class MypageNoticeModifyView(View):
    def get(self, request, club_id):
        club_notice_id = request.GET.get('id')
        club_notice = ClubNotice.objects.filter(id=club_notice_id).values('id', 'club_id', 'notice_title',
                                                                          'notice_content').first()

        context = {
            'clubNotice': club_notice,
            'club_id': club_id
        }
        return render(request, 'mypage/web/management-club-notice-modify-web.html', context)

    def post(self, request, club_id):
        club_notice_id = request.GET.get('id')
        title = request.POST.get('title')
        content = request.POST.get('content')

        club_notice = ClubNotice.objects.filter(id=club_notice_id).first()

        if club_notice:
            club_notice.notice_title = title
            club_notice.notice_content = content
            club_notice.save()

            # 상세페이지 주소로 이동하게 해야함
        return redirect(f'/member/mypage-notice/{club_id}')


class MypageSendLetterAPI(APIView):
    def post(self, request):
        letter = request.data.get('letter')

        for receiver in letter['receivers']:
            receiver_start_index = receiver.find('(') + 1
            receiver_end_index = receiver.find(')')
            receiver_email = receiver[receiver_start_index:receiver_end_index]

            receiver = Member.objects.get(member_email=receiver_email)

            sender_start_index = letter['sender'].find('(') + 1
            sender_end_index = letter['sender'].find(')')
            sender_email = letter['sender'][sender_start_index:sender_end_index]

            sender = Member.objects.get(member_email=sender_email)

            data = {
                'sender': sender,
                'receiver': receiver,
                'letter_content': letter['content']
            }

            letter = Letter.objects.create(**data)
            ReceivedLetter.objects.create(letter_id=letter.id)

            SentLetter.objects.create(letter_id=letter.id)
            Alarm.objects.create(target_id=letter.id, alarm_type=4, sender_id=letter.sender_id,
                                 receiver_id=letter.receiver_id)

        return Response('ok')


class MypageSettingView(View):
    def get(self, request, club_id):
        club = Club.objects.get(id=club_id)
        context = {
            'club_id': club_id,
            'clubName': club.club_name,
            'clubIntro': club.club_intro,
            'clubInfo': club.club_info,
            'clubProfilePath': club.club_profile_path,
            'clubBannerPath': club.club_banner_path,
            'memberNickname': club.member.member_nickname,
            'memberEmail': club.member.member_email,
            'memberPhone': club.member.member_phone,
        }

        return render(request, 'mypage/web/management-club-setting-web.html', context)

    def post(self, request, club_id):
        data = request.POST
        files = request.FILES
        club = Club.objects.get(id=club_id)
        club.club_name = data.get('club-name')
        club.club_intro = data.get('club-intro')
        club.club_info = data.get('club-details')

        for key in files:
            if key == 'club-profile':
                club.club_profile_path = files[key]
            elif key == 'background-img':
                club.club_banner_path = files[key]
        club.save()

        member_instance = Member.objects.get(id=club.member_id)
        member_instance.member_nickname = data.get('manager-name')
        member_instance.member_email = data.get('manager-email')
        member_instance.member_phone = data.get('manager-phone')
        member_instance.save()

        return redirect(f'/member/mypage-setting/{club_id}')


class MypageActivityVIEW(View):
    def get(self, request):
        return render(request, 'mypage/web/my-activity-web.html')


class MypageActivityAPIVIEW(APIView):
    @transaction.atomic
    def get(self, request, member_id, page):
        # 활동중 좋아요를 누렀는지 안눌렀는지를 따로 구분
        status_like = request.GET.get('status_like')
        # 페이지에 나타내는 데이터 숫자 선택
        row_count = 10
        # 데이터가 페이지별로 몇번부터 몇번 데이터까지인지 나타내준다.
        offset = (page - 1) * row_count
        limit = page * row_count
        # 중복을 피하기 위해 데이터를 분리해서 담아줍니다.
        activity_data = []
        # 클럽장
        activity_data += Activity.objects.filter(activitymember__member_id=member_id, status=1).values('id',
                                                                                                       'created_date',
                                                                                                       'activity_title',
                                                                                                       'thumbnail_path',
                                                                                                       'club__member_id',
                                                                                                       'activity_end',
                                                                                                       'activitymember__status')
        activity_data += Activity.objects.filter(club__member_id=member_id, status=1).values('id', 'created_date',
                                                                                             'activity_title',
                                                                                             'thumbnail_path',
                                                                                             'club__member_id',
                                                                                             'activity_end')
        # 각각의 멤버가 활동에 좋아요를 눌렀는지 확인합니다.
        for activity in activity_data:
            activity_id = activity.get('id')
            activity_like = ActivityLike.enabled_objects.filter(activity_id=activity_id, member_id=member_id)
            activity['status'] = activity_like.exists()
        # 좋아요를 누른것만 보여주기위해 분리합니다.
        if status_like == 'like':
            activity_data = ActivityLike.objects.filter(member_id=member_id, status=1).values('id', 'status',
                                                                                              'activity__thumbnail_path',
                                                                                              'activity__activity_end',
                                                                                              'activity__activity_title',
                                                                                              'activity_id')

        return Response(activity_data[offset:limit])


class MypageActivityLikeAPIVIEW(APIView):
    @transaction.atomic
    def patch(self, request, activity_id):
        # 좋아요를 눌렀을때 좋아요 만든 기록이 있다면 밑으로 만든적이 없다면 새로 만들어줍니다.
        like, created = ActivityLike.objects.get_or_create(activity_id=activity_id,
                                                           member_id=request.session['member']['id'])
        # 반전시키기
        like.status = 1 - like.status
        like.save()
        return Response('good')


class ActivityManagentView(View):
    def get(self, request):
        # 활동 관리 들어갈때 들어가는 데이터들입니다.
        # 해당 활동의 id 가져옵니다.
        activity_id = request.GET.get('activity_id')
        # 그걸로 활동 어떤건지 가져오고
        activity = Activity.objects.filter(id=activity_id).first()
        member_id = request.session['member']['id']
        # 활동에 몇명 참가했는지 나타내줍니다 / +1은 활동장은 이 테이블에 없어서 입니다.
        active_count = ActivityMember.objects.filter(activity_id=activity_id, status=1,member_id=member_id).count() + 1
        #  참가 대기 인원을 나타내 줍니다.
        wait_count = ActivityMember.objects.filter(activity_id=activity_id, status=-1).count()
        #  토탈 인원을 나타냅니다.
        total_count = active_count + wait_count
        # 활동은 모임장만 만들수 있기에 여기는 사실상 모임장만 들어오고 모임의 정보도 보여줍니다.
        club = activity.club
        club_id = club.id
        # 모임 공지사항을 최신순 4개를 나타냅니다.
        club_notices = list(ClubNotice.objects.filter(status=True, club_id=club.id).order_by('-id')[:4])
        #  틴플레이 전체 공지 중 최신 4개를 나탄냅니다.
        tennplay_notices = list(Notice.objects.filter(notice_type=0).order_by('-id')[:4])
        #  내 활동이 몇개인지 나타냅니다.
        my_activity = Activity.objects.filter(
            Q(club__member_id=member_id, status = 1) | Q(activitymember__member_id=member_id ,status = 1)).count()


        context = {'activity': activity,
                   'active_count': active_count,
                   'wait_count': wait_count,
                   'total_count': total_count,
                   'club_notices': club_notices,
                   'tennplay_notices': tennplay_notices,
                   'my_activity': my_activity,
                   'club_id':club_id
                   }

        return render(request, 'mypage/web/management-activity-web.html', context)


class ActivityListAPIView(APIView):
    @transaction.atomic
    def get(self, request, member_id, page):
        status_list = request.GET.get('status_list')
        # 페이지에 나타내는 데이터 숫자 선택
        row_count = 5
        # 데이터가 페이지별로 몇번부터 몇번 데이터까지인지 나타내준다.
        offset = (page - 1) * row_count
        limit = page * row_count
        # 전체 데이터가 몇개인지 나타내고
        total_count = 0

        total_count += Activity.objects.filter(club__member_id=member_id, status = 1).count()
        total_count += Activity.objects.filter(activitymember__member_id=member_id ,activitymember__status = 1).count()

        # 총 몇페이지인지 나타냅니다.
        total_pages = (total_count + row_count - 1) // row_count
        # 중복을 방지하기 위해 데이터를 따로 담아줍니다.
        activity_data = []
        activity_data += Activity.objects.filter(club__member_id=member_id, status = 1).values('id',
                                                                                                                'created_date',
                                                                                                                'activity_title',
                                                                                                                'activity_intro',
                                                                                                                'activity_address_location',
                                                                                                                'category__category_name',
                                                                                                                'club__member_id',
                                                                                                                'activity_end',
                                                                                                                'activity_start').order_by(
            '-activity_start')
        activity_data += Activity.objects.filter(activitymember__member_id=member_id ,activitymember__status = 1).values('id',
                                                                                                                'created_date',
                                                                                                                'activity_title',
                                                                                                                'activity_intro',
                                                                                                                'activity_address_location',
                                                                                                                'category__category_name',
                                                                                                                'club__member_id',
                                                                                                                'activity_end',
                                                                                                                'activity_start').order_by(
            '-activity_start')

        response_data = {
            'total_pages': total_pages,
            'activity_data': activity_data[offset:limit],
        }

        # 활동 시작이 가장 오래남은거부터 보여줍니다.
        if status_list == 'old/':
            # 전체 데이터가 몇개인지 나타내고
            total_count = 0

            total_count += Activity.objects.filter(club__member_id=member_id, status=1).count()
            total_count += Activity.objects.filter(activitymember__member_id=member_id, activitymember__status=1).count()
            # 총 몇페이지인지 나타냅니다.
            total_pages = (total_count + row_count - 1) // row_count
            # 중복을 방지하기 위해 데이터를 따로 담아줍니다.
            activity_data = []
            activity_data += Activity.objects.filter(club__member_id=member_id, status=1).values('id',
                                                                                                    'created_date',
                                                                                                    'activity_title',
                                                                                                    'activity_intro',
                                                                                                    'activity_address_location',
                                                                                                    'category__category_name',
                                                                                                    'club__member_id',
                                                                                                    'activity_end',
                                                                                                    'activity_start').order_by(
                'activity_start')
            activity_data += Activity.objects.filter(activitymember__member_id=member_id, activitymember__status=1).values('id',
                                                                                                            'created_date',
                                                                                                            'activity_title',
                                                                                                            'activity_intro',
                                                                                                            'activity_address_location',
                                                                                                            'category__category_name',
                                                                                                            'club__member_id',
                                                                                                            'activity_end',
                                                                                                            'activity_start').order_by(
                'activity_start')
            # 작성한 데이터를 저장합니다.
            response_data['activity_data'] = activity_data
            response_data['total_pages'] =  total_pages

        else:
            # 페이지에 나타내는 데이터 숫자 선택
            total_count = 0

            total_count += Activity.objects.filter(club__member_id=member_id, status=1).count()
            total_count += Activity.objects.filter(activitymember__member_id=member_id, activitymember__status=1).count()
            # 데이터가 페이지별로 몇번부터 몇번 데이터까지인지 나타내준다.
            total_pages = (total_count + row_count - 1) // row_count
            # 중복을 방지하기 위해 데이터를 따로 담아줍니다.
            activity_data = []
            activity_data += Activity.objects.filter(club__member_id=member_id, status=1).values('id',
                                                                                                    'created_date',
                                                                                                    'activity_title',
                                                                                                    'activity_intro',
                                                                                                    'activity_address_location',
                                                                                                    'category__category_name',
                                                                                                    'club__member_id',
                                                                                                    'activity_end',
                                                                                                    'activity_start').order_by(
                '-activity_start')
            activity_data += Activity.objects.filter(activitymember__member_id=member_id, activitymember__status=1).values('id',
                                                                                                            'created_date',
                                                                                                            'activity_title',
                                                                                                            'activity_intro',
                                                                                                            'activity_address_location',
                                                                                                            'category__category_name',
                                                                                                            'club__member_id',
                                                                                                            'activity_end',
                                                                                                            'activity_start').order_by(
                '-activity_start')


        return Response(response_data)


class ActivityMemberView(View):
    def get(self, request):
        # 페이지 이동 + 화면에 기본적으로 구성되어야하는 데이터는 활동에 담겨있어 활동id를 담아서갑니다.
        activity_id = request.GET.get('activity_id')
        context = {
            'activity_id': activity_id
        }
        return render(request, 'mypage/web/management-activity-member-web.html', context)


class ActivityMemberListAPIView(APIView):
    @transaction.atomic
    def get(self, request, member_id, page, activity_id):
        member_status = request.GET.get('member_status')
        search = request.GET.get('search')
        # 클럽장이 1페이지 상단에 있기때문에 1페이지 상단은 모임장 나머지는 5개씩 나올 수 있게 작성한다.
        row_count = 5 if page != 1 else 4
        # 데이터가 페이지별로 몇번부터 몇번 데이터까지인지 나타내준다.
        offset = (page - 1) * row_count
        limit = page * row_count
        # 전체 데이터가 몇개인지 나타내고 / 모임장 으로 인해 +1입니다.
        total_count = ActivityMember.objects.filter(
            Q(activity_id=activity_id, status=1) | Q(activity_id=activity_id, status=-1)).count() + 1
        # 총 몇페이지인지 나타냅니다.
        total_pages = (total_count + row_count - 1) // row_count
        # 1페이지 에서는 클럽장이 최 상단에 일단뜨게 해주고
        if page == 1:
            club_manager = Activity.objects.filter(id=activity_id, club__member_id=member_id).values('id',
                                                                                                     'club__member__member_nickname',
                                                                                                     'club__member__member_email',
                                                                                                     'created_date',
                                                                                                     'club__member__member_gender',
                                                                                                     'club__member__member_birth',
                                                                                                     'club__member__id'
                                                                                                     ).first()
            # 개인별로 선호 카테고리를 받아와서 뿌려줍니다.
            manager_favorite_categories = list(MemberFavoriteCategory.objects.filter(status=True,
                                                                                     member_id=club_manager.get(
                                                                                         'club__member__id')).values())
            club_manager['categories'] = manager_favorite_categories

        else:
            club_manager = None
        # 가입된 멤버의 정보를 가져옵니다.
        member_list = ActivityMember.objects.filter(
            Q(activity_id=activity_id, status=1) | Q(activity_id=activity_id, status=-1)) \
            .values('id', 'member__member_nickname', 'member__member_email', 'activity__created_date', 'status',
                    'member__member_gender', 'member__member_birth')

        # 새로운 리스트를 만들어 멤버 정보와 카테고리 정보를 함께 저장
        for member_category in member_list:
            member_id = member_category.get('member_id')
            manager_favorite_categories_add = list(
                MemberFavoriteCategory.objects.filter(status=True, member_id=member_id).values())
            member_category['categories'] = manager_favorite_categories_add

        # 이제 updated_member_list를 사용하여 결과를 처리할 수 있음

        response_data = {
            'club_manager': club_manager,
            "member_list": member_list[offset:limit],
            "total_pages": total_pages
        }
        # 필터에 따라 자료를 구분합니다.
        if member_status == 'attending':

            member_list = ActivityMember.objects.filter(activity_id=activity_id, status=1) \
                .values('id', 'member__member_nickname', 'member__member_email', 'activity__created_date', 'status',
                        'member__member_gender', 'member__member_birth')

            # 새로운 리스트를 만들어 멤버 정보와 카테고리 정보를 함께 저장
            for member_category in member_list:
                member_id = member_category.get('member_id')
                manager_favorite_categories_add = list(
                    MemberFavoriteCategory.objects.filter(status=True, member_id=member_id).values())
                member_category['categories'] = manager_favorite_categories_add

            total_count = ActivityMember.objects.filter(activity_id=activity_id, status=1).count() + 1
            total_pages = (total_count + row_count - 1) // row_count
            response_data['member_list'] = member_list
            response_data['total_pages'] = total_pages

            if search:
                member_list = ActivityMember.objects.filter(
                    Q(activity_id=activity_id, status=1, member__member_nickname__icontains=search) | Q(
                        activity_id=activity_id, status=1, member__member_email__icontains=search)) \
                    .values('id', 'member__member_nickname', 'member__member_email', 'activity__created_date', 'status',
                            'member__member_gender', 'member__member_birth')

                # 새로운 리스트를 만들어 멤버 정보와 카테고리 정보를 함께 저장
                for member_category in member_list:
                    member_id = member_category.get('member_id')
                    manager_favorite_categories_add = list(
                        MemberFavoriteCategory.objects.filter(status=True, member_id=member_id).values())
                    member_category['categories'] = manager_favorite_categories_add

                total_count = ActivityMember.objects.filter(activity_id=activity_id, status=1).count() + 1
                total_pages = (total_count + row_count - 1) // row_count
                response_data['member_list'] = member_list
                response_data['total_pages'] = total_pages

        # 필터에 따라 자료를 구분합니다.
        elif member_status == 'waiting':

            member_list = ActivityMember.objects.filter(activity_id=activity_id, status=-1) \
                .values('id', 'member__member_nickname', 'member__member_email', 'activity__created_date', 'status',
                        'member__member_gender', 'member__member_birth')

            # 새로운 리스트를 만들어 멤버 정보와 카테고리 정보를 함께 저장
            for member_category in member_list:
                member_id = member_category.get('member_id')
                manager_favorite_categories_add = list(
                    MemberFavoriteCategory.objects.filter(status=True, member_id=member_id).values())
                member_category['categories'] = manager_favorite_categories_add

            total_count = ActivityMember.objects.filter(activity_id=activity_id, status=-1).count() + 1
            total_pages = (total_count + row_count - 1) // row_count
            response_data['member_list'] = member_list
            response_data['total_pages'] = total_pages

            if search:
                member_list = ActivityMember.objects.filter(
                    Q(activity_id=activity_id, status=-1, member__member_nickname__icontains=search) | Q(
                        activity_id=activity_id, status=-1, member__member_email__icontains=search)) \
                    .values('id', 'member__member_nickname', 'member__member_email', 'activity__created_date', 'status',
                            'member__member_gender', 'member__member_birth')

                # 새로운 리스트를 만들어 멤버 정보와 카테고리 정보를 함께 저장
                for member_category in member_list:
                    member_id = member_category.get('member_id')
                    manager_favorite_categories_add = list(
                        MemberFavoriteCategory.objects.filter(status=True, member_id=member_id).values())
                    member_category['categories'] = manager_favorite_categories_add

                total_count = ActivityMember.objects.filter(activity_id=activity_id, status=-1).count() + 1
                total_pages = (total_count + row_count - 1) // row_count
                response_data['member_list'] = member_list
                response_data['total_pages'] = total_pages
        # 필터에 따라 자료를 구분합니다.
        else:
            member_list = ActivityMember.objects.filter(
                Q(activity_id=activity_id, status=1) | Q(activity_id=activity_id, status=-1)) \
                .values('id', 'member__member_nickname', 'member__member_email', 'activity__created_date', 'status',
                        'member__member_gender', 'member__member_birth')

            # 새로운 리스트를 만들어 멤버 정보와 카테고리 정보를 함께 저장
            for member_category in member_list:
                member_id = member_category.get('member_id')
                manager_favorite_categories_add = list(
                    MemberFavoriteCategory.objects.filter(status=True, member_id=member_id).values())
                member_category['categories'] = manager_favorite_categories_add

            total_count = ActivityMember.objects.filter(
                Q(activity_id=activity_id, status=1) | Q(activity_id=activity_id, status=-1)).count() + 1
            total_pages = (total_count + row_count - 1) // row_count
            response_data['member_list'] = member_list
            response_data['total_pages'] = total_pages

            if search:
                member_list = ActivityMember.objects.filter(
                    Q(activity_id=activity_id, status=1, member__member_nickname__icontains=search) | Q(
                        activity_id=activity_id, status=-1, member__member_nickname__icontains=search) | Q(
                        activity_id=activity_id, status=1, member__member_email__icontains=search) | Q(
                        activity_id=activity_id, status=-1, member__member_email__icontains=search)) \
                    .values('id', 'member__member_nickname', 'member__member_email', 'activity__created_date', 'status',
                            'member__member_gender', 'member__member_birth')

                # 새로운 리스트를 만들어 멤버 정보와 카테고리 정보를 함께 저장
                for member_category in member_list:
                    member_id = member_category.get('member_id')
                    manager_favorite_categories_add = list(
                        MemberFavoriteCategory.objects.filter(status=True, member_id=member_id).values())
                    member_category['categories'] = manager_favorite_categories_add

                total_count = ActivityMember.objects.filter(
                    Q(activity_id=activity_id, status=1) | Q(activity_id=activity_id, status=-1)).count() + 1
                total_pages = (total_count + row_count - 1) // row_count
                response_data['member_list'] = member_list
                response_data['total_pages'] = total_pages

        return Response(response_data)


class ActivityMemberUpdateAPIView(APIView):
    @transaction.atomic
    def patch(self, request, activity_member_id, activity_id):
        # 가입 신청을 하면 가입 완료상태로 바꿔주고
        ActivityMember.objects.filter(id=activity_member_id).update(status=1,updated_date=timezone.now())
        updated_member = ActivityMember.objects.get(id=activity_member_id)
        receiver_id = updated_member.member_id
        member_id = request.session['member']['id']
        #  알람을 보내줍니다.
        Alarm.objects.create(target_id=activity_id,receiver_id=receiver_id,sender_id=member_id, alarm_type=12)
        return Response('good')

    @transaction.atomic
    def delete(self, request, activity_member_id, activity_id):
        # 가입을 거절하거나 가입 취소를 시킨다면 취소 상태로 바꿔주고
        ActivityMember.objects.filter(id=activity_member_id).update(status=0,updated_date=timezone.now())
        updated_member = ActivityMember.objects.get(id=activity_member_id)
        receiver_id = updated_member.member_id
        member_id = request.session['member']['id']
        #  알람을 보내줍니다.
        Alarm.objects.create(target_id=activity_id, receiver_id=receiver_id,
                             sender_id=member_id, alarm_type=13)

        return Response('good')


class ActivityMemberWriteAPI(APIView):
    @transaction.atomic
    def post(self, request):
        # 작성된 내용을 불러옵니다.
        data = request.data
        # 그중 이메일을받아줍니다.
        receiver_email = data['receiver_email']
        receiver_instance = Member.objects.filter(member_email=receiver_email).first()
        receiver_id = receiver_instance.id
        # Letter 모델 생성
        letter = Letter.objects.create(
            receiver_id=receiver_id,
            letter_content=data['letter_content'],
            sender_id=request.session['member']['id']
        )

        # ReceivedLetter 모델 생성
        ReceivedLetter.objects.create(letter_id=letter.id)

        # SentLetter 모델 생성
        SentLetter.objects.create(letter_id=letter.id)
        # 알람을 보내줍니다.
        Alarm.objects.create(target_id=letter.id, alarm_type=4, sender_id=letter.sender_id,
                             receiver_id=letter.receiver_id)

        return Response("good")


class ActivityEditView(View):
    def get(self, request):
        # 정보 수정 전 기존에 작성한 내용을 불러옵니다.
        activity_id = request.GET.get('activity_id')
        activity = Activity.objects.filter(id=activity_id).first()
        member_id = request.session['member']['id']
        member = Member.objects.filter(id=member_id).first()
        categories = Category.objects.filter(status=True)

        context = {'activity': activity,
                   'member': member,
                   'categories': categories,
                   }

        return render(request, 'mypage/web/management-activity-edit-web.html', context)

    @transaction.atomic
    def post(self, request):
        # 작성된 내용을 가져옵니다.
        data = request.POST
        # 자신의 활동정보를 가져와 저장공간을 만듭니다.
        activity = Activity.objects.get(id=data.get('activity-id'))
        a = data.get('activity-title')
        recruit_start = make_datetime(data.get('recruit-start-date').replace(" ", ""), data.get('recruit-start-time'))
        recruit_end = make_datetime(data.get('recruit-end-date').replace(" ", ""), data.get('recruit-end-time'))
        category = Category.objects.get(id=data.get('category'))
        thumbnail = request.FILES.get('thumbnail-path')
        banner = request.FILES.get('banner-path')
        activity_start = make_datetime(data.get('activity-start-date').replace(" ", ""),
                                       data.get('activity-start-time'))
        activity_end = make_datetime(data.get('activity-end-date').replace(" ", ""), data.get('activity-end-time'))
        # 가져온 데이터들을 모두 저장해둡니다.
        activity.activity_title = a
        activity.activity_content = data.get('activity-content')
        activity.recruit_start = recruit_start
        activity.recruit_end = recruit_end
        activity.category = category
        activity.activity_intro = data.get('activity-intro')
        # 저장된 사진이 있다면 저장 없다면 기존 데이터 그대로갑니다.
        if thumbnail is not None:
            activity.thumbnail_path = thumbnail
        # 저장된 배너사진이 있다면 저장 없다면 기존 데이터 그대로 갑니다.
        if banner is not None:
            activity.banner_path = banner
        activity.activity_address_location = data.get('activity-address-location')
        activity.activity_address_detail = data.get('activity-address-detail')

        activity.activity_start = activity_start
        activity.activity_end = activity_end
        # 수정을 확정시켜줍니다.
        activity.save()

        return redirect(f'/member/activity-edit?activity_id={activity.id}')


class MypageWishlistWebView(View):
    def get(self, request):
        member = request.session.get('member')
        # latest_letter = Letter.objects.latest('id')  # 또는 필요한 기준으로 필터링
        return render(request, 'mypage/web/my-wishlist-web.html', {"member": member})


class MypageWishlistAPIView(APIView):
    @transaction.atomic
    def get(self, request, member_id, page):
        status_wishlist = request.GET.get('status_wishlist')
        row_count = 10
        offset = (page - 1) * row_count
        limit = page * row_count

        # 전체 데이터 수를 세는 쿼리
        total_count = Wishlist.objects.filter(Q(member_id=member_id, status=1)).count()

        # 전체 페이지 수 계산
        total_pages = (total_count + row_count - 1) // row_count

        # 페이지 범위에 해당하는 데이터 조회
        # 전체
        wishlists = Wishlist.objects.filter(Q(member_id=member_id), status=1).annotate(
            like_total=Count('wishlistlike__id', filter=Q(wishlistlike__status=1)),
            reply_total=Count('wishlistreply__id', filter=Q(wishlistreply__status=1)),
            category_name=F("category__category_name")) \
                        .values('wishlist_content', 'created_date', 'is_private', 'category_name', 'category',
                                'reply_total', 'like_total',
                                'id')[offset:limit]
        # 공개
        open = Wishlist.objects.filter(member_id=member_id, is_private=1, status=1).annotate(
            like_total=Count('wishlistlike__id', filter=Q(wishlistlike__status=1)),
            reply_total=Count('wishlistreply__id', filter=Q(wishlistreply__status=1)),
            category_name=F("category__category_name")) \
                   .values('wishlist_content', 'created_date', 'is_private', 'category_name', 'category', 'reply_total',
                           'like_total',
                           'id')[offset:limit]
        # 비공개
        secret = Wishlist.objects.filter(member_id=member_id, is_private=0, status=1).annotate(
            like_total=Count('wishlistlike__id', filter=Q(wishlistlike__status=1)),
            reply_total=Count('wishlistreply__id', filter=Q(wishlistreply__status=1)),
            category_name=F("category__category_name")) \
                     .values('wishlist_content', 'created_date', 'is_private', 'category_name', 'category',
                             'reply_total', 'like_total',
                             'id')[offset:limit]

        # 응답에 전체 페이지 수와 데이터 추가
        response_data = {
            'total_pages': total_pages,
            'wishlists': wishlists,

        }
        if status_wishlist == 'open':
            response_data['wishlists'] = Wishlist.objects.filter(member_id=member_id, is_private=1, status=1).annotate(
                like_total=Count('wishlistlike__id', filter=Q(wishlistlike__status=1),
                                 category=F('category__category_name')),
                reply_total=Count('wishlistreply__id', filter=Q(wishlistreply__status=1)),
                category_name=F("category__category_name")) \
                                             .values('wishlist_content', 'created_date', 'is_private', 'category_name',
                                                     'category',
                                                     'reply_total', 'like_total',
                                                     'id')[offset:limit]

            response_data['total_pages'] = (Wishlist.objects.filter(member_id=member_id, is_private=1,
                                                                    status=1).count() + row_count - 1) // row_count
        elif status_wishlist == 'secret':
            response_data['wishlists'] = Wishlist.objects.filter(member_id=member_id, is_private=0, status=1).annotate(
                like_total=Count('wishlistlike__id', filter=Q(wishlistlike__status=1)),
                reply_total=Count('wishlistreply__id', filter=Q(wishlistreply__status=1)),
                category_name=F("category__category_name")) \
                                             .values('wishlist_content', 'created_date', 'is_private', 'category_name',
                                                     'category',
                                                     'reply_total', 'like_total',
                                                     'id')[offset:limit]
            response_data['total_pages'] = (Wishlist.objects.filter(member_id=member_id, is_private=0,
                                                                    status=1).count() + row_count - 1) // row_count

        else:
            response_data['wishlists'] = Wishlist.objects.filter(Q(member_id=member_id, status=1)).annotate(
                like_total=Count('wishlistlike__id', filter=Q(wishlistlike__status=1)),
                reply_total=Count('wishlistreply__id', filter=Q(wishlistreply__status=1)),
                category_name=F("category__category_name")) \
                                             .values('wishlist_content', 'created_date', 'is_private', 'category_name',
                                                     'category',
                                                     'reply_total', 'like_total', 'id')[offset:limit]

            response_data['total_pages'] = (Wishlist.objects.filter(member_id=member_id,
                                                                    status=1).count() + row_count - 1) // row_count

        return Response(response_data)


class MypageWishlistDeleteAPIView(APIView):
    @transaction.atomic
    def delete(self, request, wishlist_id):
        wishlist = Wishlist.objects.get(id=wishlist_id)
        wishlist.status = 0
        # Wishlist.objects.filter(wishlist_id=wishlist_id).update(status=0)
        wishlist.save(update_fields=['status'])

        return Response('success')
