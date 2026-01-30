import sys
import os
import requests
import json
import argparse
from tqdm import tqdm
import time
# 将项目根目录添加到 sys.path 以便从 app 导入模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


dml_url = "http://tl.cooacloud.com/dmlv3/testcases/view"

# 3. 设置请求头 (模拟浏览器行为)
dml_headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'cookie': 'remember_token=libiao1|348082ba1e019ecfe9337b6962a9b4f2510418b7d45226aa4c0ceb51d4de88211f5986f86b1fb392402571a2f7120b2f44802c730f9279500742630283c51acd; s_dmlv3_251=ytCVjVxijZYvH7uEYZisiLh0s2fAeBJO07oKtyNXP_E; check_box=true; access_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhdCI6MTc1MTMzNDM4MywianRpIjoiZDFlYTRiYTktYWU5MS00NzA4LTg3MTEtNzhkOTA4MmNjZmYzIiwidHlwZSI6ImFjY2VzcyIsInN1YiI6ImxpYmlhbzEiLCJuYmYiOjE3NTEzMzQzODMsImV4cCI6MTc1MTkzOTE4MywibmFtZSI6Ilx1Njc0ZVx1NWY2YSIsImdyb3VwIjoyLCJyb2xlcyI6W10sInN0YXR1cyI6Ilx1NTcyOFx1ODA0YyIsImFkbWluIjpmYWxzZX0.cCk0WYulaRoYMtud-4phXLmERKIS4RncPSbhZ8LKgRQ; refresh_token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJmcmVzaCI6ZmFsc2UsImlhdCI6MTc1MTMzNDM4MywianRpIjoiMDM0ZjY3YTUtMjU3Yi00YmE3LTgzNTItNTc2NzNlZTA1YWI1IiwidHlwZSI6InJlZnJlc2giLCJzdWIiOiJsaWJpYW8xIiwibmJmIjoxNzUxMzM0MzgzLCJleHAiOjE3NjY4ODYzODN9.tYllfAwkRjPtH6RUIotsSM3wgxKSOA9-adQbktHFhLU; worklog=eyJfZnJlc2giOmZhbHNlLCJfdXNlcl9pZCI6ImxpYmlhbzEifQ.aWnnVw.ngHJqjc1lUjfgjgohaGDTLAcddg; ass_secret=mbbyKyOTzrlSyoT5Zll6Y34+bJq7zUc0; DP_Token=20a2e684-89ff-4f0f-9e3c-86ecdfb03f74; session=.eJwlzjsKwzAMANC7eO4gW7It5TLB-pgGCoWkmUrv3kDmt7xvWucexzMtn_2MR1o3T0si19EbWxeUaKNJhihkmZhar8zDXQ1JebojVmkCHdjMJ1shYJ0GwydiITce2lka4oiArNALCBEbWikO0yPkglpLN4wWKlXTFTmP2O_Na9NtvHP6_QHxBzIg.aW3ApA.5eBhsSTahnx3F1GOYj4jFqZi5Go',
    'x-csrftoken-dmlv3': 'ImVkMWEyMmRjYTBlNTcxNTQyYmIxNzhhODI3NzQ3M2M3ZjgzODA3NDgi.aW3p5g.UR17aNEEbdAkxoAqcFbJnNTZ_NI'
}

payload_dict = {
    "path_id": "658836d44ec87c06c038e930",
    "view_active": True,
    "view_inactive": False,
    "text": "",
    "tags": [],
    "fulfill_all_tags": False,
    "ignore_subfolder": False
}


dml_data = {
    'action': 'search_for_jstree_leaves',
    'payload': json.dumps(payload_dict),  # 将字典转为字符串
    'sorters': '[]',
    'page': '1',
    'size': '6175'
}



try:
    from scripts.generate_jwt import generate_jwt
except ImportError:
    # 如果直接从 scripts 目录运行时的备用方案
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from generate_jwt import generate_jwt


def create_test_case(base_url, index_uid, test_case_data):
    """通过 API 创建测试用例"""
    # 1. 生成 Token
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcHBfbmFtZSI6IjEyMzEyMyIsInNjb3BlcyI6W10sImV4cCI6MTc2OTg3NTE5OH0.f8YQTGnu7xMe67-MIENyg2DDKVR5mUWIeUweCq4qkRk"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 2. 发送请求
    url = f"{base_url}/api/v1/testcases"

    print(f"发送 POST 请求到: {url}")
    print(f"请求体: {json.dumps(test_case_data, indent=2, ensure_ascii=False)}")

    try:
        response = requests.post(url, json=test_case_data, headers=headers)

        print(f"\n响应状态码: {response.status_code}")
        try:
            print("响应内容:")
            print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        except ValueError:
            print(response.text)

    except requests.exceptions.ConnectionError:
        print(f"\n❌ 错误: 无法连接到 {base_url}，请确认服务是否正在运行。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="通过 API 添加测试用例的测试脚本")
    parser.add_argument("--url", default="http://localhost:8080", help="API 服务的基础 URL")
    parser.add_argument("--app", default="test_app", help="用于认证的应用名称")
    parser.add_argument("--index", default="test_index", help="索引唯一标识")

    args = parser.parse_args()


    response = requests.post(dml_url, data=dml_data, headers=dml_headers)

    # 6. 检查状态码并打印结果
    if response.status_code == 200:
        print("请求成功！")
        # 尝试解析 JSON 返回值
        datas = response.json()['data']
        for data in tqdm(datas[30:40]):
            print(data)
            create_test_case(args.url, args.index, data)
