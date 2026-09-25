import httpx

for url in [
    'https://day09-competition.34-142-201-239.sslip.io/',
    'https://n7-competition.pages.dev/',
]:
    r = httpx.get(url, verify=False, follow_redirects=False)
    print(f'{url}\n  -> Chuyển hướng tới: {r.headers.get("location")}\n')

    # Theo đuôi redirect xem trang đích là gì
    r2 = httpx.get(url, verify=False, follow_redirects=True)
    print(f'  -> Trang cuối cùng: {r2.url}')
    print(f'  -> Tiêu đề trang: {r2.text[:200].strip()}\n')