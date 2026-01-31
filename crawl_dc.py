import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import json
import os
from pathlib import Path

# Configuration
BASE_URL = "https://gall.dcinside.com/mgallery/board/lists/"
GALL_ID = "thesingularity"
GALL_NAME = "특이점이 온다"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}
DAYS_LIMIT = 28  # 4주간 데이터 수집

# Data directory
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def get_week_info(date):
    """ISO 8601 주차 정보 반환"""
    iso_calendar = date.isocalendar()
    year = iso_calendar[0]
    week = iso_calendar[1]
    
    # 주의 시작일과 종료일 계산
    week_start = date - timedelta(days=date.weekday())
    week_end = week_start + timedelta(days=6)
    
    return {
        'week_id': f"{year}_W{week:02d}",
        'year': year,
        'week': week,
        'week_start': week_start.strftime('%Y-%m-%d'),
        'week_end': week_end.strftime('%Y-%m-%d')
    }


def load_week_data(week_id):
    """주차별 JSON 파일 로드"""
    file_path = DATA_DIR / f"{week_id}.json"
    
    if file_path.exists():
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    return None


def save_week_data(week_id, data):
    """주차별 JSON 파일 저장"""
    file_path = DATA_DIR / f"{week_id}.json"
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 저장 완료: {file_path.name}")


def create_week_structure(week_info):
    """빈 주차 데이터 구조 생성"""
    return {
        "gallery_id": GALL_ID,
        "gallery_name": GALL_NAME,
        "week": week_info['week_id'],
        "week_start": week_info['week_start'],
        "week_end": week_info['week_end'],
        "last_updated": datetime.now().strftime('%Y-%m-%dT%H:%M:%S+09:00'),
        "posts": [],
        "total_posts": 0
    }


def parse_date(date_tag, today):
    """날짜 태그에서 datetime 객체 추출"""
    if not date_tag:
        return None
    
    # title 속성에 전체 날짜+시간 정보가 있음
    date_str = date_tag.get('title')
    if date_str:
        try:
            return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        except:
            pass
    
    # Fallback: 화면 표시 텍스트 파싱
    date_text = date_tag.get_text(strip=True)
    
    if ':' in date_text:  # HH:MM (오늘)
        try:
            hour, minute = map(int, date_text.split(':'))
            return datetime(today.year, today.month, today.day, hour, minute)
        except:
            pass
    elif '.' in date_text:
        parts = date_text.split('.')
        try:
            if len(parts) == 2:  # MM.DD (올해)
                return datetime(today.year, int(parts[0]), int(parts[1]))
            elif len(parts) == 3:  # YY.MM.DD
                year = 2000 + int(parts[0])
                return datetime(year, int(parts[1]), int(parts[2]))
        except:
            pass
    
    return None


def extract_post_data(row, today):
    """게시글 행에서 데이터 추출"""
    try:
        # 공지, 뉴스, 설문 등 특수 게시글 제외
        data_type = row.get('data-type', '')
        if 'icon_notice' in data_type:
            # 공지, 뉴스, 설문 등은 크롤링하지 않음
            return None
        
        # 제목 및 URL
        title_tag = row.select_one('td.gall_tit a')
        if not title_tag:
            return None
        
        # 댓글수 제거
        comment_tag = title_tag.select_one('.reply_numbox')
        comments = 0
        if comment_tag:
            try:
                comments = int(comment_tag.get_text(strip=True).strip('[]'))
            except:
                pass
            comment_tag.decompose()
        
        title = title_tag.get_text(strip=True)
        url = "https://gall.dcinside.com" + title_tag['href']
        
        # 게시글 번호 추출 (data-no 속성 우선 사용)
        post_id = row.get('data-no', '')
        
        if not post_id:
            # fallback: gall_num에서 추출
            num_td = row.select_one('td.gall_num')
            num_text = num_td.get_text(strip=True) if num_td else ""
            
            if not num_text.isdigit():
                # 숫자가 아니면 건너뛰기
                return None
            
            post_id = num_text
        
        # 날짜 및 시간
        date_tag = row.select_one('td.gall_date')
        post_datetime = parse_date(date_tag, today)
        
        if not post_datetime:
            return None
        
        # 작성자 정보
        writer_tag = row.select_one('td.gall_writer')
        author = ""
        author_type = "unknown"
        author_ip = ""
        
        if writer_tag:
            # data-nick 또는 data-ip 속성
            author = writer_tag.get('data-nick', '')
            author_ip = writer_tag.get('data-ip', '')
            
            if not author:
                author = writer_tag.get_text(strip=True)
            
            # 작성자 유형 판별
            if writer_tag.get('data-uid'):
                author_type = "member"
            elif author_ip:
                if author.startswith('ㅇㅇ'):
                    author_type = "semi_anonymous"
                else:
                    author_type = "ip"
            else:
                author_type = "ip"
        
        # 조회수
        views = 0
        count_tag = row.select_one('td.gall_count')
        if count_tag:
            try:
                views = int(count_tag.get_text(strip=True))
            except:
                pass
        
        # 추천수
        likes = 0
        recommend_tag = row.select_one('td.gall_recommend')
        if recommend_tag:
            try:
                likes = int(recommend_tag.get_text(strip=True))
            except:
                pass
        
        return {
            'post_id': post_id,
            'title': title,
            'author': author,
            'author_ip': author_ip,
            'author_type': author_type,
            'date': post_datetime.strftime('%Y-%m-%d'),
            'time': post_datetime.strftime('%H:%M:%S'),
            'datetime': post_datetime.strftime('%Y-%m-%dT%H:%M:%S'),
            'views': views,
            'likes': likes,
            'comments': comments,
            'url': url,
            '_datetime_obj': post_datetime  # 정렬용 임시 필드
        }
    
    except Exception as e:
        return None


def load_all_existing_ids():
    """모든 주차의 수집된 게시글 ID 집합 반환"""
    all_ids = set()
    for file_path in DATA_DIR.glob("*.json"):
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for post in data.get('posts', []):
                all_ids.add(post['post_id'])
    return all_ids

def crawl_posts():
    """게시글 크롤링"""
    print("=" * 60)
    print(f"🔍 DC 크롤러 시작")
    print(f"갤러리: {GALL_NAME} ({GALL_ID})")
    print(f"수집 기간: 최근 {DAYS_LIMIT}일")
    print("=" * 60)
    
    today = datetime.now()
    cutoff_date = today - timedelta(days=DAYS_LIMIT)
    
    # 기존에 수집된 모든 ID 로드
    existing_ids = load_all_existing_ids()
    print(f"📂 기존 수집된 게시글: {len(existing_ids)}개")
    
    all_posts = []
    page = 1
    stop_crawling = False
    new_posts_count = 0
    consecutive_dup_count = 0  # 연속 중복 카운트
    
    while not stop_crawling:
        url = f"{BASE_URL}?id={GALL_ID}&page={page}"
        print(f"\r📄 페이지 {page} 처리 중... (신규 수집: {new_posts_count}개)", end='', flush=True)
        
        try:
            response = requests.get(url, headers=HEADERS)
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"\n❌ 페이지 {page} 로드 실패: {e}")
            break
        
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.select('tr.ub-content')
        
        if not rows:
            print(f"\n⚠️  게시글 없음 (페이지 {page})")
            break
        
        for row in rows:
            post_data = extract_post_data(row, today)
            
            if not post_data:
                continue
            
            post_id = post_data['post_id']
            post_datetime = post_data['_datetime_obj']
            
            # 1. 중복 체크 (연속 5회 이상이면 중단)
            if post_id in existing_ids:
                consecutive_dup_count += 1
                if consecutive_dup_count >= 5:
                    stop_crawling = True
                    print(f"\n✋ 연속으로 5개의 중복 게시글 발견 (마지막 ID: {post_id}) → 크롤링 중단")
                    break
                continue  # 이 글은 건너뛰고 다음 글 확인
            else:
                consecutive_dup_count = 0  # 신규 글이 나오면 카운트 리셋
            
            # 2. 날짜 제한 체크
            if post_datetime >= cutoff_date:
                all_posts.append(post_data)
                new_posts_count += 1
            else:
                # 오래된 게시글 발견 → 크롤링 중단
                stop_crawling = True
                print(f"\n📅 수집 기간 초과 ({post_datetime}) → 크롤링 중단")
                break
        
        if stop_crawling:
            break
        
        page += 1
        time.sleep(0.5)  # 서버 부하 방지
    
    print(f"\n✅ 크롤링 완료! 신규 {len(all_posts)}개 수집")
    
    # _datetime_obj 필드 제거
    for post in all_posts:
        del post['_datetime_obj']
    
    return all_posts


def organize_by_week(posts):
    """게시글을 주차별로 분류"""
    weeks = {}
    
    for post in posts:
        post_date = datetime.strptime(post['datetime'], '%Y-%m-%dT%H:%M:%S')
        week_info = get_week_info(post_date)
        week_id = week_info['week_id']
        
        if week_id not in weeks:
            weeks[week_id] = {
                'info': week_info,
                'posts': []
            }
        
        weeks[week_id]['posts'].append(post)
    
    return weeks


def merge_and_save(weeks_data):
    """기존 데이터와 병합 후 저장"""
    print("\n" + "=" * 60)
    print("💾 데이터 병합 및 저장")
    print("=" * 60)
    
    for week_id, week_data in weeks_data.items():
        week_info = week_data['info']
        new_posts = week_data['posts']
        
        # 기존 데이터 로드
        existing_data = load_week_data(week_id)
        
        if existing_data:
            # 기존 게시글 ID 추출
            existing_ids = {post['post_id'] for post in existing_data['posts']}
            
            # 새 게시글만 필터링
            unique_new_posts = [post for post in new_posts if post['post_id'] not in existing_ids]
            
            # 병합
            all_posts = existing_data['posts'] + unique_new_posts
            
            print(f"📦 {week_id}: 기존 {len(existing_data['posts'])}개 + 신규 {len(unique_new_posts)}개 = 총 {len(all_posts)}개")
        else:
            # 새 파일 생성
            all_posts = new_posts
            print(f"🆕 {week_id}: 신규 파일 생성 (총 {len(all_posts)}개)")
        
        # 날짜순 정렬 (최신순)
        all_posts.sort(key=lambda x: x['datetime'], reverse=True)
        
        # 데이터 구조 생성
        week_structure = create_week_structure(week_info)
        week_structure['posts'] = all_posts
        week_structure['total_posts'] = len(all_posts)
        
        # 저장
        save_week_data(week_id, week_structure)


def main():
    """메인 실행 함수"""
    try:
        # 크롤링
        posts = crawl_posts()
        
        if not posts:
            print("⚠️  수집된 게시글이 없습니다.")
            return
        
        # 주차별 분류
        weeks_data = organize_by_week(posts)
        
        # 병합 및 저장
        merge_and_save(weeks_data)
        
        print("\n" + "=" * 60)
        print("🎉 모든 작업 완료!")
        print("=" * 60)
    
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
