/**
 * Pre-process 패널 Step 기반 워크플로우 검증 테스트
 * Playwright를 사용한 자동화 테스트
 */
import { chromium } from 'playwright';

const URL = 'http://localhost:8080';
const SCREENSHOT_PATH = 'test-preprocess-workflow-screenshot.png';

(async () => {
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
    const page = await context.newPage();

    // JS 에러 수집
    const jsErrors = [];
    page.on('pageerror', (error) => {
        jsErrors.push(error.message);
    });

    // 콘솔 에러 수집
    const consoleErrors = [];
    page.on('console', (msg) => {
        if (msg.type() === 'error') {
            consoleErrors.push(msg.text());
        }
    });

    let testResults = [];
    let passCount = 0;
    let failCount = 0;

    function assert(testName, condition, detail = '') {
        if (condition) {
            testResults.push(`  PASS: ${testName}${detail ? ' - ' + detail : ''}`);
            passCount++;
        } else {
            testResults.push(`  FAIL: ${testName}${detail ? ' - ' + detail : ''}`);
            failCount++;
        }
    }

    try {
        // ========== 검증 1: 페이지 로드 후 JS 에러 없는지 확인 ==========
        console.log('\n========================================');
        console.log('검증 1: 페이지 로드 후 JS 에러 확인');
        console.log('========================================');

        await page.goto(URL, { waitUntil: 'networkidle', timeout: 30000 });
        // 약간의 시간 대기 (JS 로드 후 에러 발생 대기)
        await page.waitForTimeout(2000);

        assert('페이지 로드 성공', true);
        assert('페이지 로드 후 JS 에러 없음', jsErrors.length === 0,
            jsErrors.length > 0 ? `에러: ${jsErrors.join(', ')}` : '에러 없음');

        // ========== 검증 2: Pre-process 탭 클릭 → panel-preprocess 표시 ==========
        console.log('\n========================================');
        console.log('검증 2: Pre-process 탭 클릭 → 패널 표시');
        console.log('========================================');

        // Pre-process 탭 찾기
        const preTab = await page.locator('.tab-btn[data-tab="preprocess"]');
        assert('Pre-process 탭 존재', await preTab.count() > 0);

        await preTab.click();
        await page.waitForTimeout(500);

        // 탭 활성화 확인
        const tabClass = await preTab.getAttribute('class');
        assert('Pre-process 탭 활성화', tabClass.includes('active'), `class="${tabClass}"`);

        // panel-preprocess 표시 확인
        const panel = await page.locator('#panel-preprocess');
        const panelDisplay = await panel.evaluate(el => getComputedStyle(el).display);
        assert('panel-preprocess 표시됨', panelDisplay !== 'none', `display="${panelDisplay}"`);

        // ========== 검증 3: 워크플로우 순서대로 요소 확인 ==========
        console.log('\n========================================');
        console.log('검증 3: 워크플로우 순서 요소 확인');
        console.log('========================================');

        // 브러쉬 선택 섹션
        const brushRadius = await page.locator('#bc-brush-radius');
        assert('bc-brush-radius 슬라이더 존재', await brushRadius.count() > 0);

        const selectionCount = await page.locator('#bc-selection-count');
        assert('bc-selection-count 존재', await selectionCount.count() > 0);

        const btnClearSelection = await page.locator('#btn-clear-selection');
        assert('btn-clear-selection 버튼 존재', await btnClearSelection.count() > 0);

        // Step 1: Fixed BC
        const btnApplyFixed = await page.locator('#btn-apply-fixed');
        assert('btn-apply-fixed 버튼 존재', await btnApplyFixed.count() > 0);

        // Step 2: Force BC
        const forceMagnitude = await page.locator('#force-magnitude');
        assert('force-magnitude 슬라이더 존재', await forceMagnitude.count() > 0);

        const forceDirectionDisplay = await page.locator('#force-direction-display');
        assert('force-direction-display 존재', await forceDirectionDisplay.count() > 0);

        const btnResetForceDir = await page.locator('#btn-reset-force-dir');
        assert('btn-reset-force-dir 버튼 존재', await btnResetForceDir.count() > 0);

        const btnApplyForce = await page.locator('#btn-apply-force');
        assert('btn-apply-force 버튼 존재', await btnApplyForce.count() > 0);

        // BC 관리
        const btnClearBc = await page.locator('#btn-clear-bc');
        assert('btn-clear-bc 버튼 존재', await btnClearBc.count() > 0);

        // Step 3: 재료 설정
        const materialTarget = await page.locator('#material-target');
        assert('material-target 셀렉트 존재', await materialTarget.count() > 0);

        const materialPreset = await page.locator('#material-preset');
        assert('material-preset 셀렉트 존재', await materialPreset.count() > 0);

        const btnAssignMaterial = await page.locator('#btn-assign-material');
        assert('btn-assign-material 버튼 존재', await btnAssignMaterial.count() > 0);

        // 워크플로우 순서 확인 (DOM 순서)
        const panelHTML = await panel.innerHTML();
        const brushIdx = panelHTML.indexOf('bc-brush-radius');
        const step1Idx = panelHTML.indexOf('btn-apply-fixed');
        const step2Idx = panelHTML.indexOf('btn-apply-force');
        const clearBcIdx = panelHTML.indexOf('btn-clear-bc');
        const step3Idx = panelHTML.indexOf('btn-assign-material');

        assert('순서: 브러쉬 → Step1(Fixed)', brushIdx < step1Idx,
            `brush@${brushIdx} < fixed@${step1Idx}`);
        assert('순서: Step1(Fixed) → Step2(Force)', step1Idx < step2Idx,
            `fixed@${step1Idx} < force@${step2Idx}`);
        assert('순서: Step2(Force) → BC관리(Clear)', step2Idx < clearBcIdx,
            `force@${step2Idx} < clearBc@${clearBcIdx}`);
        assert('순서: BC관리 → Step3(재료)', clearBcIdx < step3Idx,
            `clearBc@${clearBcIdx} < material@${step3Idx}`);

        // ========== 검증 4: Fixed/Force 라디오 버튼이 없는지 확인 ==========
        console.log('\n========================================');
        console.log('검증 4: bc-type 라디오 버튼 없음 확인');
        console.log('========================================');

        const bcTypeRadios = await page.locator('input[name="bc-type"]');
        const bcTypeCount = await bcTypeRadios.count();
        assert('input[name="bc-type"] 라디오 버튼 없음', bcTypeCount === 0,
            `발견된 개수: ${bcTypeCount}`);

        // ========== 검증 5: Force 방향 표시 항상 보이는지 확인 ==========
        console.log('\n========================================');
        console.log('검증 5: Force 방향 표시 가시성 확인');
        console.log('========================================');

        const forceDir = await page.locator('#force-direction-display');
        const forceDirText = await forceDir.textContent();
        assert('방향 표시 텍스트 확인', forceDirText.includes('0.00') && forceDirText.includes('-1.00'),
            `텍스트: "${forceDirText}"`);

        // display: none이 아닌지 확인 (자기 자신과 부모 요소들)
        const forceDirVisible = await forceDir.evaluate(el => {
            let current = el;
            while (current && current !== document.body) {
                const style = getComputedStyle(current);
                if (style.display === 'none' || style.visibility === 'hidden') {
                    return { visible: false, element: current.tagName + (current.id ? '#' + current.id : ''),
                             display: style.display, visibility: style.visibility };
                }
                current = current.parentElement;
            }
            return { visible: true };
        });
        assert('Force 방향 표시 항상 보임 (display:none 아님)', forceDirVisible.visible,
            forceDirVisible.visible ? '보임' : `숨겨짐: ${JSON.stringify(forceDirVisible)}`);

        // ========== 검증 6: Step별 색상 구분 확인 ==========
        console.log('\n========================================');
        console.log('검증 6: Step별 border-left 색상 확인');
        console.log('========================================');

        // Step 1: Fixed BC - 초록 border
        const step1Section = await page.locator('#btn-apply-fixed').locator('..');
        const step1Border = await step1Section.evaluate(el => getComputedStyle(el).borderLeftColor);
        // rgb(0, 204, 68) = #00cc44
        assert('Step 1 (Fixed) border-left 초록색',
            step1Border.includes('0, 204, 68') || step1Border.includes('0,204,68'),
            `color: ${step1Border}`);

        // Step 2: Force BC - 빨강 border
        const step2Section = await page.locator('#btn-apply-force').locator('..');
        const step2Border = await step2Section.evaluate(el => getComputedStyle(el).borderLeftColor);
        // rgb(255, 34, 34) = #ff2222
        assert('Step 2 (Force) border-left 빨강색',
            step2Border.includes('255, 34, 34') || step2Border.includes('255,34,34'),
            `color: ${step2Border}`);

        // Step 3: 재료 - 파랑 border
        const step3Section = await page.locator('#btn-assign-material').locator('..');
        const step3Border = await step3Section.evaluate(el => getComputedStyle(el).borderLeftColor);
        // rgb(25, 118, 210) = #1976d2
        assert('Step 3 (재료) border-left 파랑색',
            step3Border.includes('25, 118, 210') || step3Border.includes('25,118,210'),
            `color: ${step3Border}`);

        // ========== 검증 7: 스크린샷 ==========
        console.log('\n========================================');
        console.log('검증 7: 스크린샷 캡처');
        console.log('========================================');

        await page.screenshot({ path: SCREENSHOT_PATH, fullPage: false });
        assert('스크린샷 저장 완료', true, SCREENSHOT_PATH);

        // ========== 검증 8: 콘솔 JS 에러 최종 확인 ==========
        console.log('\n========================================');
        console.log('검증 8: 최종 JS 에러 확인');
        console.log('========================================');

        assert('최종 JS pageerror 없음', jsErrors.length === 0,
            jsErrors.length > 0 ? `에러: ${jsErrors.join('; ')}` : '에러 없음');
        assert('최종 콘솔 error 없음', consoleErrors.length === 0,
            consoleErrors.length > 0 ? `에러: ${consoleErrors.join('; ')}` : '에러 없음');

    } catch (err) {
        console.error('테스트 실행 중 오류:', err.message);
        testResults.push(`  FAIL: 테스트 실행 오류 - ${err.message}`);
        failCount++;
    } finally {
        // 결과 요약 출력
        console.log('\n========================================');
        console.log('        테스트 결과 요약');
        console.log('========================================');
        testResults.forEach(r => console.log(r));
        console.log('========================================');
        console.log(`  총: ${passCount + failCount} | PASS: ${passCount} | FAIL: ${failCount}`);
        console.log('========================================');

        await browser.close();
        process.exit(failCount > 0 ? 1 : 0);
    }
})();
