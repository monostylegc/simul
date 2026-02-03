"""FEA 시각화 브라우저 테스트."""

import asyncio
from playwright.async_api import async_playwright


async def test_fea_viewer():
    """실제 브라우저 창에서 FEA 뷰어 테스트."""
    async with async_playwright() as p:
        # 브라우저 실행
        browser = await p.chromium.launch(
            headless=False,
            args=['--enable-webgl', '--ignore-gpu-blocklist', '--use-gl=desktop']
        )

        page = await browser.new_page(viewport={'width': 1400, 'height': 900})

        # 콘솔 로그 캡처
        logs = []
        page.on('console', lambda msg: logs.append(f"[{msg.type}] {msg.text}"))

        print("1. 페이지 로딩...")
        await page.goto('http://localhost:8081')
        await page.wait_for_timeout(2000)

        # WebGL 확인
        webgl = await page.evaluate('''() => {
            const canvas = document.querySelector('canvas');
            if (!canvas) return 'No canvas';
            const gl = canvas.getContext('webgl') || canvas.getContext('webgl2');
            return gl ? 'WebGL OK' : 'WebGL failed';
        }''')
        print(f"   WebGL: {webgl}")

        await page.screenshot(path='fea_01_initial.png')
        print("   스크린샷: fea_01_initial.png")

        print("\n2. 샘플 데이터 로드...")
        await page.click('#btn-load-sample')
        await page.wait_for_timeout(1000)
        await page.screenshot(path='fea_02_sample_loaded.png')
        print("   스크린샷: fea_02_sample_loaded.png")

        print("\n3. von Mises Strain 모드...")
        await page.click('[data-mode="strain"]')
        await page.wait_for_timeout(500)
        await page.screenshot(path='fea_03_strain_mode.png')
        print("   스크린샷: fea_03_strain_mode.png")

        print("\n4. Damage 모드...")
        await page.click('[data-mode="damage"]')
        await page.wait_for_timeout(500)
        await page.screenshot(path='fea_04_damage_mode.png')
        print("   스크린샷: fea_04_damage_mode.png")

        print("\n5. 파티클 크기 조정...")
        await page.fill('#particle-size', '2')
        await page.dispatch_event('#particle-size', 'input')
        await page.wait_for_timeout(500)
        await page.screenshot(path='fea_05_large_particles.png')
        print("   스크린샷: fea_05_large_particles.png")

        print("\n6. Top View...")
        await page.click('#btn-top-view')
        await page.wait_for_timeout(500)
        await page.screenshot(path='fea_06_top_view.png')
        print("   스크린샷: fea_06_top_view.png")

        # 콘솔 로그 출력
        print("\n=== Console Logs ===")
        for log in logs[:20]:  # 처음 20개만
            print(log)

        print("\n테스트 완료! 5초 후 브라우저 닫힘...")
        await page.wait_for_timeout(5000)
        await browser.close()


if __name__ == '__main__':
    asyncio.run(test_fea_viewer())
