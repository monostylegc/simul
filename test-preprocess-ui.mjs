/**
 * Pre-process UI 테스트
 * DOM 상태 기반으로 검증 (let 변수는 window 접근 불가)
 */
import { chromium } from '@playwright/test';

const URL = 'http://localhost:8080';
let passed = 0, failed = 0;

function check(label, ok) {
    if (ok) { console.log(`  ✓ ${label}`); passed++; }
    else    { console.log(`  ✗ ${label}`); failed++; }
}

(async () => {
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    // JS 에러 수집
    const jsErrors = [];
    page.on('pageerror', err => jsErrors.push(err.message));

    console.log('=== Pre-process UI 테스트 ===\n');

    // ── 페이지 로드 ──
    console.log('[1] 페이지 로드');
    await page.goto(URL, { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000); // STL 로드 + 렌더링 대기

    const title = await page.title();
    check(`타이틀: "${title}"`, title.includes('Spine'));

    // JS 에러 체크 (로드 시)
    check(`JS 에러 없음 (${jsErrors.length}개)`, jsErrors.length === 0);
    if (jsErrors.length > 0) jsErrors.forEach(e => console.log(`    → ${e}`));

    // 모델 로드 확인
    const modelList = await page.$eval('#model-list', el => el.textContent);
    check(`모델 로드됨`, modelList.includes('L4') || modelList.includes('L5'));

    // ── Pre-process 메뉴 ──
    console.log('\n[2] Pre-process 메뉴');
    const menuBtn = page.locator('button[data-menu="preprocess"]');
    const menuText = await menuBtn.textContent();
    check(`메뉴 이름: "${menuText.trim()}"`, menuText.trim() === 'Pre-process');

    await menuBtn.click();
    await page.waitForTimeout(300);
    const dropdownOpen = await page.$eval('#dropdown-preprocess', el => el.classList.contains('open'));
    check('드롭다운 열림', dropdownOpen);

    // ── Brush Select 활성화 ──
    console.log('\n[3] BC 브러쉬 모드 활성화');
    await page.click('#mi-select-faces');
    await page.waitForTimeout(3000); // 복셀 초기화 대기

    const toolText = await page.$eval('#current-tool', el => el.textContent);
    check(`상태바 도구: "${toolText}"`, toolText === 'BC Brush');

    const panelBCVisible = await page.$eval('#panel-bc', el => el.style.display !== 'none');
    check('BC 패널 표시됨', panelBCVisible);

    const bcTypeFixed = await page.$eval('input[name="bc-type"][value="fixed"]', el => el.checked);
    check('Fixed 라디오 기본 선택', bcTypeFixed);

    // 좌클릭 카메라 비활성 확인
    const mouseButtonsStr = await page.evaluate(() => {
        // OrbitControls의 mouseButtons 직접 확인 (controls는 let이지만 함수 내에서 접근)
        try {
            const c = document.querySelector('canvas').__controls_ref;
            return JSON.stringify(c?.mouseButtons);
        } catch(e) { return 'N/A'; }
    });
    // controls 직접 접근이 안되면 다른 방법으로 확인
    console.log(`  ℹ mouseButtons: ${mouseButtonsStr}`);

    // ── BC 브러쉬 칠하기 (좌클릭) ──
    console.log('\n[4] BC 브러쉬 칠하기');
    const canvasBox = await page.locator('#canvas-container').boundingBox();
    const cx = canvasBox.x + canvasBox.width / 2;
    const cy = canvasBox.y + canvasBox.height / 2;

    // 호버 → 프리뷰 확인
    await page.mouse.move(cx, cy);
    await page.waitForTimeout(500);

    // 좌클릭 (칠하기)
    await page.mouse.click(cx, cy);
    await page.waitForTimeout(300);

    let selCountText = await page.$eval('#bc-selection-count', el => el.textContent);
    const selCount1 = parseInt(selCountText) || 0;
    check(`클릭 후 선택 복셀: ${selCount1}`, selCount1 > 0);

    // 드래그 (추가 칠하기)
    await page.mouse.move(cx - 40, cy);
    await page.waitForTimeout(100);
    await page.mouse.down();
    for (let i = 0; i < 8; i++) {
        await page.mouse.move(cx - 40 + i * 10, cy, { steps: 2 });
        await page.waitForTimeout(50);
    }
    await page.mouse.up();
    await page.waitForTimeout(300);

    selCountText = await page.$eval('#bc-selection-count', el => el.textContent);
    const selCount2 = parseInt(selCountText) || 0;
    check(`드래그 후 선택 복셀: ${selCount2} (≥${selCount1})`, selCount2 >= selCount1);

    // ── Force 모드 전환 ──
    console.log('\n[5] Force 모드');
    await page.click('input[name="bc-type"][value="force"]');
    await page.waitForTimeout(300);

    const forceSectionVisible = await page.$eval('#force-direction-section', el => el.style.display !== 'none');
    check('Force 방향 섹션 표시', forceSectionVisible);

    const forceDirText = await page.$eval('#force-direction-display', el => el.textContent);
    check(`Force 방향 표시: "${forceDirText}"`, forceDirText.includes('-1.00'));

    const forceMagValue = await page.$eval('#force-magnitude', el => el.value);
    check(`Force 크기 기본값: ${forceMagValue}N`, forceMagValue === '100');

    // ── Fixed로 복귀 ──
    await page.click('input[name="bc-type"][value="fixed"]');
    await page.waitForTimeout(200);
    const forceSectionHidden = await page.$eval('#force-direction-section', el => el.style.display === 'none');
    check('Fixed 전환 시 Force 섹션 숨김', forceSectionHidden);

    // ── BC 적용 ──
    console.log('\n[6] BC 적용');
    // 먼저 다시 칠하기
    await page.mouse.click(cx, cy);
    await page.waitForTimeout(300);

    await page.click('#btn-apply-bc');
    await page.waitForTimeout(300);

    selCountText = await page.$eval('#bc-selection-count', el => el.textContent);
    check(`적용 후 선택 초기화: "${selCountText}"`, selCountText === '0');

    // ── 드릴 모드 ──
    console.log('\n[7] 드릴 모드');
    await page.click('button[data-menu="modeling"]');
    await page.waitForTimeout(200);
    await page.click('#mi-drill');
    await page.waitForTimeout(500);

    const drillToolText = await page.$eval('#current-tool', el => el.textContent);
    check(`상태바 도구: "${drillToolText}"`, drillToolText === 'Drill');

    // 드릴 패널 표시
    const drillPanelVisible = await page.$eval('#panel-drill', el => el.style.display !== 'none');
    check('드릴 패널 표시', drillPanelVisible);

    // 캔버스에 좌클릭 (드릴)
    await page.mouse.move(cx, cy);
    await page.waitForTimeout(300);
    await page.mouse.click(cx, cy);
    await page.waitForTimeout(500);

    // 드릴 후 상태바에 Tool이 아직 Drill인지 확인 (충돌 없이 작동)
    const afterDrillTool = await page.$eval('#current-tool', el => el.textContent);
    check(`드릴 후 도구 유지: "${afterDrillTool}"`, afterDrillTool === 'Drill');

    // ── 재료 대상 목록 ──
    console.log('\n[8] 재료 대상 목록');
    const matTargets = await page.$$eval('#material-target option', opts => opts.map(o => o.value));
    check(`대상 목록: [${matTargets.join(', ')}]`, matTargets.length > 1 && matTargets.includes('__all__'));

    // ── 스크린샷 ──
    await page.screenshot({ path: 'test-preprocess-screenshot.png', fullPage: true });

    // ── 최종 JS 에러 체크 ──
    console.log('\n[9] JS 에러 종합');
    check(`JS 에러: ${jsErrors.length}개`, jsErrors.length === 0);
    if (jsErrors.length > 0) jsErrors.forEach(e => console.log(`    → ${e}`));

    // ── 요약 ──
    console.log(`\n=== 결과: ${passed} passed, ${failed} failed ===`);

    await browser.close();
    process.exit(failed > 0 ? 1 : 0);
})();
