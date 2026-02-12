/**
 * Spine Surgery Simulator 웹 UI 테스트 (Playwright)
 *
 * 테스트 절차:
 * 1. http://localhost:8000 접속
 * 2. 페이지 로드 확인
 * 3. STL 모델 자동 로드 확인
 * 4~14. 각종 UI 인터랙션 및 스크린샷
 */

import { chromium } from 'playwright';
import { fileURLToPath } from 'url';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');

// 결과 보고
const results = [];
function report(step, name, passed, detail = '') {
    const status = passed ? 'PASS' : 'FAIL';
    const msg = `[${status}] Step ${step}: ${name}${detail ? ' - ' + detail : ''}`;
    results.push(msg);
    console.log(msg);
}

(async () => {
    // 스크린샷 디렉토리 생성
    const fs = await import('fs');
    if (!fs.existsSync(SCREENSHOT_DIR)) {
        fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
    }

    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
    const page = await context.newPage();

    // 콘솔 메시지 수집
    const consoleMsgs = [];
    page.on('console', msg => consoleMsgs.push(`[${msg.type()}] ${msg.text()}`));

    try {
        // Step 1: 브라우저로 http://localhost:8000 접속
        console.log('\n=== Step 1: 브라우저로 접속 ===');
        try {
            await page.goto('http://localhost:8000', { timeout: 10000 });
            report(1, '페이지 접속', true, 'http://localhost:8000');
        } catch (e) {
            report(1, '페이지 접속', false, e.message);
            throw new Error('서버에 접속할 수 없습니다. http://localhost:8000 서버가 실행 중인지 확인하세요.');
        }

        // Step 2: 페이지 로드 확인 (타이틀)
        console.log('\n=== Step 2: 페이지 로드 확인 ===');
        const title = await page.title();
        report(2, '페이지 타이틀 확인', title === 'Spine Surgery Simulator', `타이틀: "${title}"`);

        // Step 3: STL 모델 자동 로드 확인
        console.log('\n=== Step 3: STL 모델 로드 확인 ===');
        // 모델 로드는 비동기이므로 잠시 대기
        await page.waitForTimeout(3000);
        const modelListText = await page.$eval('#model-list', el => el.textContent.trim()).catch(() => '');
        const modelListHTML = await page.$eval('#model-list', el => el.innerHTML).catch(() => '');
        const hasModels = modelListText.length > 0;
        report(3, 'STL 모델 자동 로드', hasModels, hasModels ? `모델 목록: ${modelListText.substring(0, 100)}` : '모델 목록 비어있음 (수동 로드 필요)');

        // Step 4: 스크린샷 (초기 상태)
        console.log('\n=== Step 4: 초기 상태 스크린샷 ===');
        const ss1 = path.join(SCREENSHOT_DIR, '01_initial_state.png');
        await page.screenshot({ path: ss1, fullPage: false });
        report(4, '초기 상태 스크린샷', true, ss1);

        // Step 5: "Analysis" 버튼 클릭
        console.log('\n=== Step 5: Analysis 버튼 클릭 ===');
        const analysisBtn = page.locator('button[data-tool="analysis"]');
        const analysisBtnExists = await analysisBtn.count() > 0;
        if (analysisBtnExists) {
            await analysisBtn.click();
            await page.waitForTimeout(500);
            report(5, 'Analysis 버튼 클릭', true);
        } else {
            report(5, 'Analysis 버튼 클릭', false, 'Analysis 버튼을 찾을 수 없음');
        }

        // Step 6: Analysis 패널 표시 확인
        console.log('\n=== Step 6: Analysis 패널 표시 확인 ===');
        const analysisPanelVisible = await page.locator('#analysis-panel').isVisible().catch(() => false);
        report(6, 'Analysis 패널 표시', analysisPanelVisible);

        // WebSocket 연결 상태 확인
        console.log('\n=== WebSocket 연결 상태 확인 ===');
        const wsStatusText = await page.$eval('#ws-status', el => el.textContent.trim()).catch(() => '확인 불가');
        const wsStatusColor = await page.$eval('#ws-status', el => getComputedStyle(el).color).catch(() => '');
        report('WS', 'WebSocket 연결 상태', true, `서버: ${wsStatusText} (색상: ${wsStatusColor})`);

        // Step 7: 스크린샷 (Analysis 모드)
        console.log('\n=== Step 7: Analysis 모드 스크린샷 ===');
        const ss2 = path.join(SCREENSHOT_DIR, '02_analysis_mode.png');
        await page.screenshot({ path: ss2, fullPage: false });
        report(7, 'Analysis 모드 스크린샷', true, ss2);

        // Step 8: BC 타입을 Force로 변경
        console.log('\n=== Step 8: BC 타입 Force 변경 ===');
        const forceRadio = page.locator('input[name="bc-type"][value="force"]');
        const forceRadioExists = await forceRadio.count() > 0;
        if (forceRadioExists) {
            await forceRadio.click();
            await page.waitForTimeout(300);
            const forceInputsVisible = await page.locator('#force-inputs').isVisible().catch(() => false);
            report(8, 'BC Force 변경 및 Force 입력 UI', forceInputsVisible, forceInputsVisible ? 'Force 입력 UI 표시됨' : 'Force 입력 UI 미표시');
        } else {
            report(8, 'BC Force 라디오 버튼', false, 'Force 라디오 버튼을 찾을 수 없음');
        }

        // Step 9: 재료 프리셋 드롭다운 확인
        console.log('\n=== Step 9: 재료 프리셋 드롭다운 확인 ===');
        const materialSelect = page.locator('#material-preset');
        const materialExists = await materialSelect.count() > 0;
        if (materialExists) {
            const options = await page.$$eval('#material-preset option', opts => opts.map(o => `${o.value}: ${o.textContent}`));
            report(9, '재료 프리셋 드롭다운', true, `옵션: ${options.join(', ')}`);
        } else {
            report(9, '재료 프리셋 드롭다운', false, '드롭다운을 찾을 수 없음');
        }

        // Step 10: 솔버 드롭다운 확인
        console.log('\n=== Step 10: 솔버 드롭다운 확인 ===');
        const solverSelect = page.locator('#solver-method');
        const solverExists = await solverSelect.count() > 0;
        if (solverExists) {
            const options = await page.$$eval('#solver-method option', opts => opts.map(o => `${o.value}: ${o.textContent}`));
            report(10, '솔버 드롭다운', true, `옵션: ${options.join(', ')}`);
        } else {
            report(10, '솔버 드롭다운', false, '드롭다운을 찾을 수 없음');
        }

        // Step 11: Post-process 모드 버튼 클릭
        console.log('\n=== Step 11: Post-process 모드 전환 ===');
        const postModeBtn = page.locator('#btn-post-mode');
        const postModeBtnExists = await postModeBtn.count() > 0;
        if (postModeBtnExists) {
            await postModeBtn.click();
            await page.waitForTimeout(500);
            const postSectionVisible = await page.locator('#post-section').isVisible().catch(() => false);
            const preSectionHidden = !(await page.locator('#pre-section').isVisible().catch(() => true));
            report(11, 'Post-process 모드 전환', postSectionVisible,
                `Post-section 표시: ${postSectionVisible}, Pre-section 숨김: ${preSectionHidden}`);
        } else {
            report(11, 'Post-process 버튼', false, '버튼을 찾을 수 없음');
        }

        // Step 12: 스크린샷 (Post-process 모드)
        console.log('\n=== Step 12: Post-process 모드 스크린샷 ===');
        const ss3 = path.join(SCREENSHOT_DIR, '03_postprocess_mode.png');
        await page.screenshot({ path: ss3, fullPage: false });
        report(12, 'Post-process 모드 스크린샷', true, ss3);

        // Step 13: Pre-process 모드로 돌아가기
        console.log('\n=== Step 13: Pre-process 모드 복귀 ===');
        const preModeBtn = page.locator('#btn-pre-mode');
        const preModeBtnExists = await preModeBtn.count() > 0;
        if (preModeBtnExists) {
            await preModeBtn.click();
            await page.waitForTimeout(500);
            const preSectionVisible = await page.locator('#pre-section').isVisible().catch(() => false);
            report(13, 'Pre-process 모드 복귀', preSectionVisible, `Pre-section 표시: ${preSectionVisible}`);
        } else {
            report(13, 'Pre-process 버튼', false, '버튼을 찾을 수 없음');
        }

        // Step 14: 최종 스크린샷
        console.log('\n=== Step 14: 최종 스크린샷 ===');
        const ss4 = path.join(SCREENSHOT_DIR, '04_final_state.png');
        await page.screenshot({ path: ss4, fullPage: false });
        report(14, '최종 스크린샷', true, ss4);

    } catch (e) {
        console.error('\n!!! 테스트 중 오류 발생:', e.message);
    } finally {
        await browser.close();
    }

    // 최종 보고서
    console.log('\n' + '='.repeat(60));
    console.log('        테스트 결과 보고서');
    console.log('='.repeat(60));
    results.forEach(r => console.log(r));

    const passed = results.filter(r => r.includes('[PASS]')).length;
    const failed = results.filter(r => r.includes('[FAIL]')).length;
    console.log('='.repeat(60));
    console.log(`총 ${passed + failed}개 항목: ${passed}개 성공, ${failed}개 실패`);
    console.log('='.repeat(60));

    // 콘솔 에러 출력
    const errors = consoleMsgs.filter(m => m.startsWith('[error]'));
    if (errors.length > 0) {
        console.log('\n브라우저 콘솔 에러:');
        errors.forEach(e => console.log('  ' + e));
    }
})();
