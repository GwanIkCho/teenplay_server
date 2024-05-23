### teenplay ai project

##### teenchin 추천 시스템

---

### 기획배경

사용을 잘 하지 않는 사람들에게 같이 할수 있는 유저를 추천해주면서
함께할 수 있는 상황을 유도한다.

문화를 같이 즐긴다는 슬로건처럼 함께 할 수 있는 사람들을 무꺼주는 것도 중요하다
같이 할 수있는 사람드를 추천하고 함께하는것을 유도한다?

기대효과

위시리스트 작성과 개인 선호 카테고리 선택을 유도하면서
자신의 좋아하는 활동의 노출을 증대시키고 유저의 참여를 유도할 수 있다.

둘다 요로코롬한 느낌으로 정리합시다.

---

### 프로젝트

#### 데이터 수집

-   기본적으로 틴친추천 서비스는 개인의 관심 카테고리, 본인이 작성한 위시리스트와 태그를 기반으로 추천하기 때문에
    유저들이 직접 작성한 _member_favorite_category_, _wishlist_, _wishlist_tag_ 테이블을 사용합니다.

<img src='./image/img2.png'>
<img src='./image/img1.png'>

-   각 테이블 별로 status가 1은 활성화 0은 비활성화 상태입니다.
    status가 1 즉, 활성화 상태인 데이터만 사용합니다.

-   3개의 테이블을 member_id를 기준으로 group_by를 사용하여 묶어주고 **cosine similarity**를 사용하기 위해 하나의 피쳐로 만들어줍니다.

<img src='./image/img3.png'>

각 피쳐별있는 카테고리는 따로 테이블을 만들어 fk를 받아서 사용하였습니다. 각 number는 각각 의미하는 문자로 변형시켜줍니다.

-   각 피쳐들중 사용하기 _wishlit_content_,*tag_name*을 붙여서 하나의 피쳐로 만들어줍니다.

<details>
  <summary>Click data preprocessing</summary>

```sql
CREATE OR REPLACE VIEW member_wishlist_view AS
SELECT
    m.id AS id,
    CONCAT(
        GROUP_CONCAT(DISTINCT CONCAT(IFNULL(w.wishlist_content, ''), ' ', IFNULL(wt.tag_name, '')) ORDER BY w.wishlist_content SEPARATOR ' '),
        ' ',
        GROUP_CONCAT(DISTINCT
            CASE
                WHEN c.id = 1 THEN '카테고리_취미'
                WHEN c.id = 2 THEN '카테고리_문화'
                WHEN c.id = 3 THEN '카테고리_액티비티'
                WHEN c.id = 4 THEN '카테고리_음식'
                WHEN c.id = 5 THEN '카테고리_여행'
                WHEN c.id = 6 THEN '카테고리_발전'
                WHEN c.id = 7 THEN '카테고리_동네모임'
                WHEN c.id = 8 THEN '카테고리_데이트'
                WHEN c.id = 9 THEN '카테고리_투자'
                WHEN c.id = 10 THEN '카테고리_언어'
                WHEN c.id = 11 THEN '카테고리_공부'
                WHEN c.id = 12 THEN '카테고리_축제'
                WHEN c.id = 13 THEN '카테고리_기타'
                ELSE ''
            END
            ORDER BY c.id SEPARATOR ' ')
    ) AS wishlist_content
FROM
    tbl_member m
LEFT JOIN
    tbl_member_favorite_category mfc ON m.id = mfc.member_id AND mfc.status = 1
LEFT JOIN
    tbl_category c ON mfc.category_id = c.id
LEFT JOIN
    tbl_wishlist w ON m.id = w.member_id AND w.status = 1
LEFT JOIN
    tbl_wishlist_tag wt ON w.id = wt.wishlist_id AND wt.status = 1
GROUP BY
    m.id;
```

</details>

<img src='./image/img4.png'>

-   이렇게 완성된 view를 df로 만들어 주고 **cosine similarity**를 진행합니다.

<details>
  <summary>Click data preprocessing</summary>

```python
def get_member_wishlist_data():
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, wishlist_content FROM member_wishlist_view")
        rows = cursor.fetchall()

    # 가져온 데이터를 데이터프레임으로 변환하고 열 이름을 명시적으로 변경
    df = pd.DataFrame(rows, columns=['id', 'wishlist_content'])

    return df

```

</details>

-   먼저 **cosine similarity**란  
    **_관련된 사진하나_**
-   x축과 좌표까지 이르는 점선 주변에 있는 점들이 유사도가
    높다고 측정, 평행을 이루고 방향이 같은 백터간의
    유사도가 높다고 판단한다.

-   설명설명 설명을 해봅시다잉

<details>
  <summary>Click data preprocessing</summary>

```python
class member_id_target():
    def member_id_target(self, member_target_number):

        data = get_member_wishlist_data()
        result_df = data.wishlist_content

        from sklearn.feature_extraction.text import CountVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        count_v = CountVectorizer()
        count_metrix = count_v.fit_transform(result_df)


        c_s = cosine_similarity(count_metrix)

        def get_index_from_title(member_id):
            return data[data.id == member_id].index[0]

        def get_title_from_index(index):
            return data[data.index == index]['id'].values[0]

        movie_title = member_target_number
        movie_index = get_index_from_title(movie_title)
        recommended_movie = sorted(list(enumerate(c_s[movie_index])), key=lambda x: x[1], reverse=True)

        target_member = []
        for movie in recommended_movie[1:30]:
            target_member.append(get_title_from_index(movie[0]))

        return target_member
```

</details>

### 검증

<img src='./image/img5.png'>

-   검증용으로 member_id를 입력하고 상위 9개를 뽑아봅니다.

<img src='./image/img6.png' width='50%' height='50%'>

-   모든 category_id는 같은것을 확인할 수 있으며 상위 4개는 같은 활동을
    희망하는 것을 볼 수 있다.

### 실제 데이터 추출

-   실제 데이터중 친구추가 관련 활동 경력이 없는 유저를 구분하여 화면에 나타날 9명을 추출한다.

<details>
<summary>Click data preprocessing</summary>

```python
    def get_unmatched_senders(self, member_id):
        results = member_id_target().member_id_target(member_id)
        friends_filter = Q(sender_id__in=results, receiver_id=member_id) | Q(sender_id=member_id,receiver_id__in=results)
        friend_ids = set(friend['sender_id'] for friend in friends).union(
            set(friend['receiver_id'] for friend in friends))
        unmatched_senders = [sender_id for sender_id in results if sender_id not in friend_ids]
        return unmatched_senders

    def get_teenchin_add(self, unmatched_senders):
        return list(Member.objects.filter(id__in=unmatched_senders).values('id', 'member_nickname'))

    def get(self, request, member_id, page):
        member_id = request.session.get('member').get('id')
        status_letter = request.GET.get('status_teenchin')
        search_text = request.GET.get('search', '')[:-1]
        row_count = 9
        offset = (page - 1) * row_count
        limit = page * row_count

        unmatched_senders = self.get_unmatched_senders(member_id)
        teenchin_add = self.get_teenchin_add(unmatched_senders)

        response_data = {
            'teenchin': teenchin[offset:limit],
            'teenchin_add': teenchin_add[:9]
        }

        return Response(response_data)
```

</details>

-   유저의 친추정보 밑에 추천친구를 나타내면서 유저들에게 정보를 제공한다.

<img src='./image/img7.png'>

---

### 마무리

-   이러한 서비스를 통해서 틴플이 추구하는 건 어떤것이며
    이러한 서비스를 계속 기획해서 안정적인 서비스를 제공할것이다.

이런느낌의 기획설명 및 회사 비전소개하는 느낌으로 추가하기

느낀점 + 트러블슈팅 적어줘야 합니다^^
