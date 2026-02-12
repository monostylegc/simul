/**
 * 탭 기반 UI 검증 테스트 스크립트
 * Playwright를 사용하여 http://localhost:8080 의 탭 UI 검증
 */
import { chromium } from 'playwright';

const BASE_URL = 'http://localhost:8080';
let passed = 0;
let failed = 0;
const errors = [];

function assert(condition, testName) {
    if (condition) {
        console.log(`  [PASS] ${testName}`);
        passed++;
    } else {
        console.log(`  [FAIL] ${testName}`);
        failed++;
        errors.push(testName);
    }
}

(async () => {
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
    const page = await context.newPage();

    // JS 에러 수집
    const jsErrors = [];
    page.on('pageerror', err => {
        jsErrors.push(err.message);
    });
    // 콘솔 에러 수집
    const consoleErrors = [];
    page.on('console', msg => {
        if (msg.type() === 'error') {
            consoleErrors.push(msg.text());
        }
    });

    console.log('\n========================================');
    console.log(' 탭 기반 UI 검증 테스트');
    console.log('========================================\n');

    // 페이지 로드
    console.log('[1] 페이지 로드 및 JS 에러 확인');
    await page.goto(BASE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000); // JS 초기화 대기

    // 스크린샷: 초기 상태
    await page.screenshot({ path: 'test-screenshots/01-initial.png', fullPage: false });
    console.log('  → 스크린샷: test-screenshots/01-initial.png');

    // 에러 체크 (Three.js 로드 실패 등 심각한 에러만 필터)
    const criticalErrors = jsErrors.filter(e => !e.includes('WebSocket') && !e.includes('ws://'));
    assert(criticalErrors.length === 0, `페이지 로드 시 JS 에러 없음 (발견: ${criticalErrors.length}개${criticalErrors.length > 0 ? ' - ' + criticalErrors.join('; ') : ''})`);

    // ──────────────────────────────────────
    console.log('\n[2] 탭 바에 6개 탭 표시 확인');
    const expectedTabs = ['File', 'Modeling', 'Pre-process', 'Solve', 'Post-process', 'View'];
    const tabButtons = await page.$$eval('.tab-btn', els => els.map(el => el.textContent.trim()));
    assert(tabButtons.length === 6, `탭 버튼 6개 존재 (실제: ${tabButtons.length}개)`);
    for (const name of expectedTabs) {
        assert(tabButtons.includes(name), `"${name}" 탭 존재`);
    }

    // ──────────────────────────────────────
    console.log('\n[3] Undo/Redo 아이콘 버튼 확인');
    const undoBtn = await page.$('#btn-undo-top');
    const redoBtn = await page.$('#btn-redo-top');
    assert(undoBtn !== null, 'Undo 버튼 (#btn-undo-top) 존재');
    assert(redoBtn !== null, 'Redo 버튼 (#btn-redo-top) 존재');

    // 상단 우측에 위치하는지 확인 (menubar-right 안에 있는지)
    const undoInRight = await page.$eval('#menubar-right', el => {
        const undo = el.querySelector('#btn-undo-top');
        const redo = el.querySelector('#btn-redo-top');
        return undo !== null && redo !== null;
    });
    assert(undoInRight, 'Undo/Redo 버튼이 상단 우측(#menubar-right)에 위치');

    // ──────────────────────────────────────
    console.log('\n[4] File 탭 기본 활성 상태 확인');
    const fileTabActive = await page.$eval('.tab-btn[data-tab="file"]', el => el.classList.contains('active'));
    assert(fileTabActive, 'File 탭이 active 클래스 보유');

    const filePanelVisible = await page.$eval('#panel-file', el => el.style.display !== 'none');
    assert(filePanelVisible, 'File 패널(#panel-file) 표시됨');

    // Models/Import/좌표설정 섹션 확인
    const filePanelSections = await page.$$eval('#panel-file .prop-section-title', els => els.map(el => el.textContent.trim()));
    assert(filePanelSections.includes('Models'), 'File 패널에 "Models" 섹션 존재');
    assert(filePanelSections.includes('Import'), 'File 패널에 "Import" 섹션 존재');
    assert(filePanelSections.includes('좌표 설정'), 'File 패널에 "좌표 설정" 섹션 존재');

    // 스크린샷: File 탭
    await page.screenshot({ path: 'test-screenshots/02-file-tab.png', fullPage: false });

    // ──────────────────────────────────────
    console.log('\n[5] 각 탭 클릭하여 패널 전환 확인');

    // --- Modeling 탭 ---
    console.log('\n  [5-1] Modeling 탭');
    await page.click('.tab-btn[data-tab="modeling"]');
    await page.waitForTimeout(300);
    const modelingVisible = await page.$eval('#panel-modeling', el => el.style.display !== 'none');
    const modelingActive = await page.$eval('.tab-btn[data-tab="modeling"]', el => el.classList.contains('active'));
    assert(modelingVisible, 'panel-modeling 표시됨');
    assert(modelingActive, 'Modeling 탭 active');

    // Drill 관련 요소
    const drillBtn = await page.$('#btn-toggle-drill');
    const drillRadius = await page.$('#drill-radius');
    assert(drillBtn !== null, 'Drill 토글 버튼 존재');
    assert(drillRadius !== null, 'Drill 반경 슬라이더 존재');
    await page.screenshot({ path: 'test-screenshots/03-modeling-tab.png', fullPage: false });

    // File 패널이 숨겨졌는지 확인
    const filePanelHidden = await page.$eval('#panel-file', el => el.style.display === 'none');
    assert(filePanelHidden, 'File 패널 숨겨짐 (탭 전환 시)');

    // --- Pre-process 탭 ---
    console.log('\n  [5-2] Pre-process 탭');
    await page.click('.tab-btn[data-tab="preprocess"]');
    await page.waitForTimeout(300);
    const preprocessVisible = await page.$eval('#panel-preprocess', el => el.style.display !== 'none');
    assert(preprocessVisible, 'panel-preprocess 표시됨');

    // BC 타입 라디오 확인
    const bcRadios = await page.$$eval('input[name="bc-type"]', els => els.map(el => el.value));
    assert(bcRadios.includes('fixed'), 'BC 타입 "fixed" 라디오 존재');
    assert(bcRadios.includes('force'), 'BC 타입 "force" 라디오 존재');

    // 브러쉬 설정 확인
    const brushRadius = await page.$('#bc-brush-radius');
    assert(brushRadius !== null, '브러쉬 반경 슬라이더 존재');
    await page.screenshot({ path: 'test-screenshots/04-preprocess-tab.png', fullPage: false });

    // --- Solve 탭 ---
    console.log('\n  [5-3] Solve 탭');
    await page.click('.tab-btn[data-tab="solve"]');
    await page.waitForTimeout(300);
    const solveVisible = await page.$eval('#panel-solve', el => el.style.display !== 'none');
    assert(solveVisible, 'panel-solve 표시됨');

    // 솔버 선택
    const solverSelect = await page.$('#solver-method');
    assert(solverSelect !== null, '솔버 선택 드롭다운 존재');
    const solverOptions = await page.$$eval('#solver-method option', els => els.map(el => el.value));
    assert(solverOptions.includes('fem'), 'FEM 솔버 옵션 존재');
    assert(solverOptions.includes('pd'), 'PD 솔버 옵션 존재');
    assert(solverOptions.includes('spg'), 'SPG 솔버 옵션 존재');

    // 해석 실행 버튼
    const runBtn = await page.$('#btn-run-analysis');
    assert(runBtn !== null, '"해석 실행" 버튼 존재');
    const runBtnText = await page.$eval('#btn-run-analysis', el => el.textContent.trim());
    assert(runBtnText.includes('해석 실행'), '해석 실행 버튼 텍스트 확인');
    await page.screenshot({ path: 'test-screenshots/05-solve-tab.png', fullPage: false });

    // --- Post-process 탭 ---
    console.log('\n  [5-4] Post-process 탭');
    await page.click('.tab-btn[data-tab="postprocess"]');
    await page.waitForTimeout(300);
    const postprocessVisible = await page.$eval('#panel-postprocess', el => el.style.display !== 'none');
    assert(postprocessVisible, 'panel-postprocess 표시됨');

    // 시각화 모드 확인
    const vizSelect = await page.$('#viz-mode');
    assert(vizSelect !== null, '시각화 모드 드롭다운 존재');
    const vizOptions = await page.$$eval('#viz-mode option', els => els.map(el => el.value));
    assert(vizOptions.includes('displacement'), '변위(displacement) 시각화 옵션 존재');
    assert(vizOptions.includes('stress'), '응력(stress) 시각화 옵션 존재');
    assert(vizOptions.includes('damage'), '손상(damage) 시각화 옵션 존재');
    await page.screenshot({ path: 'test-screenshots/06-postprocess-tab.png', fullPage: false });

    // --- View 탭 ---
    console.log('\n  [5-5] View 탭');
    await page.click('.tab-btn[data-tab="view"]');
    await page.waitForTimeout(300);
    const viewVisible = await page.$eval('#panel-view', el => el.style.display !== 'none');
    assert(viewVisible, 'panel-view 표시됨');

    // 카메라 프리셋
    const camReset = await page.$('#btn-cam-reset');
    assert(camReset !== null, '카메라 Reset 버튼 존재');
    const camFront = await page.$('#btn-cam-front');
    const camBack = await page.$('#btn-cam-back');
    const camTop = await page.$('#btn-cam-top');
    const camBottom = await page.$('#btn-cam-bottom');
    const camLeft = await page.$('#btn-cam-left');
    const camRight = await page.$('#btn-cam-right');
    assert(camFront && camBack && camTop && camBottom && camLeft && camRight, '6방향 카메라 프리셋 버튼 모두 존재');

    // Up 축 라디오
    const upAxisRadios = await page.$$eval('input[name="up-axis"]', els => els.map(el => el.value));
    assert(upAxisRadios.includes('y') && upAxisRadios.includes('z'), 'Up 축 Y/Z 라디오 버튼 존재');

    // 조명 슬라이더
    const ambientSlider = await page.$('#ambient-intensity');
    const dirSlider = await page.$('#dir-intensity');
    assert(ambientSlider !== null, 'Ambient 밝기 슬라이더 존재');
    assert(dirSlider !== null, 'Directional 밝기 슬라이더 존재');

    // 배경색 선택
    const bgSelect = await page.$('#bg-color');
    assert(bgSelect !== null, '배경색 드롭다운 존재');

    // Grid/Axes 체크박스
    const chkGrid = await page.$('#chk-grid');
    const chkAxes = await page.$('#chk-axes');
    assert(chkGrid !== null, 'Grid 체크박스 존재');
    assert(chkAxes !== null, 'Axes 체크박스 존재');
    await page.screenshot({ path: 'test-screenshots/07-view-tab.png', fullPage: false });

    // ──────────────────────────────────────
    console.log('\n[6] View 탭 - 배경색 "검정"으로 변경');
    await page.selectOption('#bg-color', '#1a1a1a');
    await page.waitForTimeout(500);

    // 캔버스 배경 변경 확인 (renderer setClearColor를 통해 변경됨)
    // canvas 요소의 css backgroundColor이 아닌, Three.js renderer의 clearColor로 변경됨
    // 스크린샷으로 확인
    await page.screenshot({ path: 'test-screenshots/08-bg-black.png', fullPage: false });
    const bgValue = await page.$eval('#bg-color', el => el.value);
    assert(bgValue === '#1a1a1a', '배경색 드롭다운이 검정(#1a1a1a)으로 설정됨');
    console.log('  → 스크린샷으로 캔버스 배경 변경 확인: test-screenshots/08-bg-black.png');

    // ──────────────────────────────────────
    console.log('\n[7] View 탭 - Grid/Axes 체크박스 동작 확인');

    // Grid 해제
    const gridCheckedBefore = await page.$eval('#chk-grid', el => el.checked);
    assert(gridCheckedBefore === true, 'Grid 체크박스 초기 상태: 체크됨');
    await page.click('#chk-grid');
    await page.waitForTimeout(300);
    const gridCheckedAfter = await page.$eval('#chk-grid', el => el.checked);
    assert(gridCheckedAfter === false, 'Grid 체크박스 클릭 후: 해제됨');

    // Axes 해제
    const axesCheckedBefore = await page.$eval('#chk-axes', el => el.checked);
    assert(axesCheckedBefore === true, 'Axes 체크박스 초기 상태: 체크됨');
    await page.click('#chk-axes');
    await page.waitForTimeout(300);
    const axesCheckedAfter = await page.$eval('#chk-axes', el => el.checked);
    assert(axesCheckedAfter === false, 'Axes 체크박스 클릭 후: 해제됨');
    await page.screenshot({ path: 'test-screenshots/09-grid-axes-off.png', fullPage: false });

    // 다시 체크
    await page.click('#chk-grid');
    await page.click('#chk-axes');
    await page.waitForTimeout(300);
    const gridRecheck = await page.$eval('#chk-grid', el => el.checked);
    const axesRecheck = await page.$eval('#chk-axes', el => el.checked);
    assert(gridRecheck === true, 'Grid 재체크 후: 체크됨');
    assert(axesRecheck === true, 'Axes 재체크 후: 체크됨');
    await page.screenshot({ path: 'test-screenshots/10-grid-axes-on.png', fullPage: false });

    // ──────────────────────────────────────
    console.log('\n[8] 최종 JS 에러 확인');
    const finalCriticalErrors = jsErrors.filter(e => !e.includes('WebSocket') && !e.includes('ws://'));
    assert(finalCriticalErrors.length === 0, `전체 테스트 중 심각한 JS 에러 없음 (발견: ${finalCriticalErrors.length}개)`);

    if (consoleErrors.length > 0) {
        const critConsole = consoleErrors.filter(e => !e.includes('WebSocket') && !e.includes('ws://') && !e.includes('ERR_CONNECTION_REFUSED'));
        if (critConsole.length > 0) {
            console.log(`  [INFO] 콘솔 에러 (WebSocket 제외): ${critConsole.length}개`);
            critConsole.forEach(e => console.log(`    - ${e}`));
        }
        assert(critConsole.length === 0, `콘솔에 심각한 에러 없음 (WebSocket 관련 제외)`);
    } else {
        assert(true, '콘솔 에러 없음');
    }

    if (jsErrors.length > 0) {
        console.log('\n  [INFO] 전체 JS 에러 목록:');
        jsErrors.forEach(e => console.log(`    - ${e}`));
    }

    // ──────────────────────────────────────
    console.log('\n========================================');
    console.log(` 결과: ${passed} passed, ${failed} failed`);
    console.log('========================================');
    if (errors.length > 0) {
        console.log('\n실패한 항목:');
        errors.forEach(e => console.log(`  - ${e}`));
    }
    console.log('');

    await browser.close();
    process.exit(failed > 0 ? 1 : 0);
})();
