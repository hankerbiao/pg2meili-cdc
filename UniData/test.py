import requests

code = '00869944'
url = f'https://soa.com.cn/solr/personcore/select?hl.fl=fulltext&hl=on&q=fulltext:{code}&rows=10&start=0&t=1769649159'

headers = {
    'Cookie': 'aiToken=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI5MjRiMTkyZi0wNjEyLTQ4M2QtOTk2Zi0yMmUyNzkzODI2ODEiLCJzdWIiOiJXZWIgQVBJIFBhc3Nwb3J0IiwiYXBwX2lkIjoiOTI0YjE5MmYtMDYxMi00ODNkLTk5NmYtMjJlMjc5MzgyNjgxIiwiYXBwX2NvZGUiOiIyOU1lRGpqM21ZQkZMME40IiwiZW5kX3VzZXJfaWQiOiJjODQyMDEwYi1jYTRkLTRlYTctOGY4OS1mNWE4N2Q5OTMzNzUifQ.OroyJwL153-SDnYOr8ClhUaI5MIgzf0x2IG4EViOLcA; ass_secret=mbbyKyOTzrnhq3p1xd704sVl3OsMXvsN; DP_Token=4fca6bf2-99c0-4408-81cc-cbf44f013d37; JSESSIONID=6C1B6F7566EFB08C6922D3E995723C3B'
}
response = requests.get(url, headers=headers)
docs = response.json()['response']['docs'][0]
psname = docs['psnname'][0]
_id = docs['id']
print(f"id:{_id},psname:{psname}")
