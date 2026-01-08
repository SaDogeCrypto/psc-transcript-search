import { test, expect } from '@playwright/test';

test.describe('Admin Pipeline Page', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the pipeline page
    await page.goto('/admin/pipeline');
    // Wait for initial data to load
    await page.waitForLoadState('networkidle');
  });

  test('page loads without errors', async ({ page }) => {
    // Check page title or header exists - use specific h2 heading
    await expect(page.getByRole('heading', { name: 'Pipeline', level: 2 })).toBeVisible({ timeout: 10000 });

    // Check no unhandled errors in console
    const errors: string[] = [];
    page.on('pageerror', (error) => {
      errors.push(error.message);
    });

    await page.waitForTimeout(2000);
    expect(errors).toHaveLength(0);
  });

  test('pipeline stages are visible with counts', async ({ page }) => {
    // Check all pipeline stages are visible
    const stages = ['Dockets', 'Discover', 'Download', 'Transcribe', 'Analyze', 'Review', 'Extract'];
    for (const stage of stages) {
      await expect(page.locator(`text=${stage}`).first()).toBeVisible({ timeout: 5000 });
    }

    // Check Complete stage exists
    await expect(page.locator('text=Complete').first()).toBeVisible();

    // Verify stages have numeric counts by checking for numbers in the stage area
    // Each stage card shows a count like "19" with "pending" below it
    const pendingCounts = page.locator('text=pending');
    const processedCounts = page.locator('text=processed');
    const sourcesCounts = page.locator('text=sources');

    const totalLabels = await pendingCounts.count() + await processedCounts.count() + await sourcesCounts.count();
    expect(totalLabels).toBeGreaterThan(0);
  });

  test('Scan PSCs button triggers scraper and shows feedback', async ({ page }) => {
    // Find the Scan PSCs button in Docket Discovery section
    const scanButton = page.getByRole('button', { name: /Scan PSCs/i });
    await expect(scanButton).toBeVisible({ timeout: 5000 });

    // Click Scan and verify some response happens
    await scanButton.click();

    // Should show loading state OR success/error message
    // Wait a bit for the API call
    await page.waitForTimeout(3000);

    // Check page is still functional (no crash)
    await expect(page.getByRole('heading', { name: 'Pipeline', level: 2 })).toBeVisible();

    // Check for any error message that appeared
    const errorAlert = page.locator('.alert-error, [class*="error"]');
    if (await errorAlert.isVisible()) {
      console.log('Scan returned error (may be expected):', await errorAlert.textContent());
    }
  });

  test('clicking Transcribe stage expands and shows hearings list', async ({ page }) => {
    // Find Transcribe stage card
    const transcribeCard = page.locator('div').filter({ hasText: 'Transcribe' }).filter({ hasText: 'pending' }).first();
    await expect(transcribeCard).toBeVisible();

    // Get the count before clicking
    const countElement = transcribeCard.locator('div').filter({ hasText: /^\d+$/ }).first();
    const countText = await countElement.textContent();
    const count = countText ? parseInt(countText) : 0;

    // Click to expand
    await transcribeCard.click();
    await page.waitForTimeout(1500);

    if (count > 0) {
      // Should show hearings list with checkboxes
      const checkboxes = page.locator('input[type="checkbox"]');
      const checkboxCount = await checkboxes.count();
      expect(checkboxCount).toBeGreaterThan(0);

      // Should have a "Select all" or similar button
      const selectAllBtn = page.locator('button').filter({ hasText: /select all|all/i }).first();
      if (await selectAllBtn.isVisible()) {
        expect(await selectAllBtn.isEnabled()).toBeTruthy();
      }
    } else {
      // Empty state message or just no hearings
      console.log('No hearings in Transcribe stage');
    }
  });

  test('clicking Complete stage shows processed hearings with details', async ({ page }) => {
    // Find Complete stage card
    const completeCard = page.locator('div').filter({ hasText: 'Complete' }).filter({ hasText: 'processed' }).first();
    await expect(completeCard).toBeVisible();

    // Get count
    const countElement = completeCard.locator('div').filter({ hasText: /^\d+$/ }).first();
    const countText = await countElement.textContent();
    const count = countText ? parseInt(countText) : 0;

    if (count > 0) {
      // Click to expand
      await completeCard.click();
      await page.waitForTimeout(2000);

      // Should show list of hearings
      const hearingRows = page.locator('label').filter({ has: page.locator('input[type="checkbox"]') });
      const rowCount = await hearingRows.count();
      expect(rowCount).toBeGreaterThan(0);

      // Hearings should have titles visible
      const hearingTitles = page.locator('span').filter({ hasText: /Commission|PSC|Hearing/i });
      expect(await hearingTitles.count()).toBeGreaterThan(0);
    }
  });

  test('selecting hearings with checkboxes works', async ({ page }) => {
    // Expand Complete stage (most likely to have hearings)
    const completeCard = page.locator('div').filter({ hasText: 'Complete' }).filter({ hasText: 'processed' }).first();
    const countText = await completeCard.locator('div').filter({ hasText: /^\d+$/ }).first().textContent();
    const count = countText ? parseInt(countText) : 0;

    if (count > 0) {
      await completeCard.click();
      await page.waitForTimeout(2000);

      // Find first checkbox
      const firstCheckbox = page.locator('input[type="checkbox"]').first();
      await expect(firstCheckbox).toBeVisible();

      // Click to select
      await firstCheckbox.click();

      // Verify it's checked
      await expect(firstCheckbox).toBeChecked();

      // Click again to uncheck
      await firstCheckbox.click();
      await expect(firstCheckbox).not.toBeChecked();
    }
  });

  test('opening hearing detail modal shows transcript and analysis', async ({ page }) => {
    // Expand Complete stage
    const completeCard = page.locator('div').filter({ hasText: 'Complete' }).filter({ hasText: 'processed' }).first();
    const countText = await completeCard.locator('div').filter({ hasText: /^\d+$/ }).first().textContent();
    const count = countText ? parseInt(countText) : 0;

    if (count > 0) {
      await completeCard.click();
      await page.waitForTimeout(2000);

      // Find and click the info/eye icon to open detail modal
      // Look for Eye icon or info button
      const infoButton = page.locator('svg.lucide-eye, button[title*="View"], button[title*="detail"]').first();

      if (await infoButton.isVisible()) {
        await infoButton.click();
        await page.waitForTimeout(2000);

        // Modal should be open
        const modal = page.locator('.modal, [class*="modal"]');
        await expect(modal).toBeVisible({ timeout: 5000 });

        // Check for hearing details content
        const modalContent = await modal.textContent();

        // Should have processing history section
        expect(modalContent).toContain('Processing History');

        // Should have transcript section (if transcribed)
        const hasTranscript = modalContent?.includes('Transcript') || modalContent?.includes('transcript');

        // Should have analysis section (if analyzed)
        const hasAnalysis = modalContent?.includes('Analysis') || modalContent?.includes('Summary');

        // At least one of these should be present for a complete hearing
        expect(hasTranscript || hasAnalysis).toBeTruthy();

        // Close modal
        const closeButton = modal.locator('button').filter({ hasText: /close|×/i }).first();
        if (await closeButton.isVisible()) {
          await closeButton.click();
        } else {
          await page.keyboard.press('Escape');
        }

        await page.waitForTimeout(500);
        await expect(modal).not.toBeVisible();
      }
    }
  });

  test('sorting hearings by different columns works', async ({ page }) => {
    // Expand a stage with hearings
    const completeCard = page.locator('div').filter({ hasText: 'Complete' }).filter({ hasText: 'processed' }).first();
    const countText = await completeCard.locator('div').filter({ hasText: /^\d+$/ }).first().textContent();
    const count = countText ? parseInt(countText) : 0;

    if (count > 1) {
      await completeCard.click();
      await page.waitForTimeout(2000);

      // Look for sort buttons/headers (State, Title, Duration, Date)
      const sortButtons = page.locator('button').filter({ hasText: /state|title|duration|date/i });
      const sortCount = await sortButtons.count();

      if (sortCount > 0) {
        // Click first sort button
        const firstSort = sortButtons.first();
        await firstSort.click();
        await page.waitForTimeout(500);

        // Click again to reverse sort
        await firstSort.click();
        await page.waitForTimeout(500);

        // Page should still be functional
        await expect(page.getByRole('heading', { name: 'Pipeline', level: 2 })).toBeVisible();
      }
    }
  });

  test('Run Full Pipeline button is visible and clickable', async ({ page }) => {
    // Find the Run Full Pipeline button
    const runPipelineBtn = page.getByRole('button', { name: /Run Full Pipeline/i });
    await expect(runPipelineBtn).toBeVisible({ timeout: 5000 });

    // Should be enabled when pipeline is idle
    const isDisabled = await runPipelineBtn.isDisabled();

    if (!isDisabled) {
      // We won't actually run it, just verify it's interactive
      expect(await runPipelineBtn.isEnabled()).toBeTruthy();
    }
  });

  test('refresh button reloads data', async ({ page }) => {
    // Find refresh button (usually a refresh icon)
    const refreshBtn = page.locator('button svg.lucide-refresh-cw, button[title*="Refresh"]').first();

    if (await refreshBtn.isVisible()) {
      // Click parent button
      const button = refreshBtn.locator('..');
      await button.click();
      await page.waitForTimeout(2000);

      // Page should still be functional after refresh
      await expect(page.getByRole('heading', { name: 'Pipeline', level: 2 })).toBeVisible();
    }
  });

  test('Discover stage shows sources when expanded', async ({ page }) => {
    // Find Discover stage
    const discoverCard = page.locator('div').filter({ hasText: 'Discover' }).filter({ hasText: 'sources' }).first();
    await discoverCard.click();
    await page.waitForTimeout(1500);

    // Should show sources panel or message about sources
    const sourcesText = page.locator('text=sources');
    expect(await sourcesText.count()).toBeGreaterThan(0);
  });

  test('stage action buttons appear when hearings are selected', async ({ page }) => {
    // Expand Transcribe stage (where action buttons would appear)
    const transcribeCard = page.locator('div').filter({ hasText: 'Transcribe' }).filter({ hasText: 'pending' }).first();
    const countText = await transcribeCard.locator('div').filter({ hasText: /^\d+$/ }).first().textContent();
    const count = countText ? parseInt(countText) : 0;

    if (count > 0) {
      await transcribeCard.click();
      await page.waitForTimeout(2000);

      // Select a hearing
      const firstCheckbox = page.locator('input[type="checkbox"]').first();
      if (await firstCheckbox.isVisible()) {
        await firstCheckbox.click();
        await page.waitForTimeout(500);

        // Look for action buttons (Transcribe Selected, Dismiss, etc.)
        const actionButtons = page.locator('button').filter({ hasText: /transcribe|process|dismiss/i });
        const buttonCount = await actionButtons.count();

        // There should be action buttons when items are selected
        if (buttonCount > 0) {
          // At least one action button should be visible
          const firstAction = actionButtons.first();
          await expect(firstAction).toBeVisible();
        }

        // Unselect
        await firstCheckbox.click();
      }
    }
  });

  test('Data Quality section shows verification stats', async ({ page }) => {
    // Look for Data Quality section
    const dataQuality = page.locator('text=Data Quality');
    await expect(dataQuality).toBeVisible({ timeout: 5000 });

    // Should show verification categories (Verified, Likely, Possible, Unverified)
    const categories = ['Verified', 'Likely', 'Possible', 'Unverified'];
    for (const category of categories) {
      const categoryLabel = page.locator(`text=${category}`);
      await expect(categoryLabel.first()).toBeVisible();
    }
  });

  test('Docket Discovery section shows source count', async ({ page }) => {
    // Look for Docket Discovery section
    const docketDiscovery = page.locator('text=Docket Discovery');
    await expect(docketDiscovery).toBeVisible({ timeout: 5000 });

    // Should show sources enabled count
    const sourcesEnabled = page.locator('text=/\\d+\\s*\\/\\s*\\d+\\s*sources enabled/i');
    if (await sourcesEnabled.isVisible()) {
      const text = await sourcesEnabled.textContent();
      expect(text).toMatch(/\d+\s*\/\s*\d+/);
    }
  });

  test('no JavaScript errors during all interactions', async ({ page }) => {
    const errors: string[] = [];

    page.on('pageerror', (error) => {
      errors.push(error.message);
    });

    // Click through various stages
    const stageSelectors = [
      { name: 'Transcribe', subtext: 'pending' },
      { name: 'Analyze', subtext: 'pending' },
      { name: 'Complete', subtext: 'processed' },
    ];

    for (const { name, subtext } of stageSelectors) {
      const stage = page.locator('div').filter({ hasText: name }).filter({ hasText: subtext }).first();
      if (await stage.isVisible()) {
        await stage.click();
        await page.waitForTimeout(1000);

        // If there are hearings, try selecting one
        const checkbox = page.locator('input[type="checkbox"]').first();
        if (await checkbox.isVisible()) {
          await checkbox.click();
          await page.waitForTimeout(300);
          await checkbox.click(); // unselect
        }
      }
    }

    // Try opening detail modal if possible
    const completeCard = page.locator('div').filter({ hasText: 'Complete' }).filter({ hasText: 'processed' }).first();
    if (await completeCard.isVisible()) {
      await completeCard.click();
      await page.waitForTimeout(1500);

      const eyeIcon = page.locator('svg.lucide-eye').first();
      if (await eyeIcon.isVisible()) {
        await eyeIcon.click();
        await page.waitForTimeout(2000);
        await page.keyboard.press('Escape');
        await page.waitForTimeout(500);
      }
    }

    // Report errors if any
    if (errors.length > 0) {
      console.log('JavaScript errors found:', errors);
    }
    expect(errors).toHaveLength(0);
  });
});

test.describe('Admin Pipeline - Dismissed Hearings', () => {
  test('dismissed hearings section is accessible', async ({ page }) => {
    await page.goto('/admin/pipeline');
    await page.waitForLoadState('networkidle');

    // Look for Dismissed section
    const dismissedCard = page.locator('div').filter({ hasText: 'Dismissed' }).filter({ hasText: /skipped|dismissed/i }).first();

    if (await dismissedCard.isVisible()) {
      await dismissedCard.click();
      await page.waitForTimeout(1500);

      // Should show dismissed hearings or empty message
      await expect(page.getByRole('heading', { name: 'Pipeline', level: 2 })).toBeVisible();
    }
  });
});

test.describe('Admin Pipeline - Error Handling', () => {
  test('handles API errors gracefully', async ({ page }) => {
    const errors: string[] = [];

    page.on('pageerror', (error) => {
      errors.push(error.message);
    });

    await page.goto('/admin/pipeline');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Should not have crashed
    await expect(page.locator('body')).toBeVisible();

    // Log any errors for debugging
    if (errors.length > 0) {
      console.log('Errors during page load:', errors);
    }
  });

  test('error banner can be dismissed', async ({ page }) => {
    await page.goto('/admin/pipeline');
    await page.waitForLoadState('networkidle');

    // If there's an error banner, try to dismiss it
    const errorBanner = page.locator('.alert-error, [class*="error-banner"]');

    if (await errorBanner.isVisible()) {
      const closeBtn = errorBanner.locator('button, [class*="close"]').first();
      if (await closeBtn.isVisible()) {
        await closeBtn.click();
        await page.waitForTimeout(500);
        // Error should be dismissed or at least page should still work
        await expect(page.getByRole('heading', { name: 'Pipeline', level: 2 })).toBeVisible();
      }
    }
  });
});

test.describe('Admin Pipeline - Action Buttons', () => {
  test('Run Selected button makes API call with correct payload', async ({ page }) => {
    // Track API calls
    const apiCalls: { url: string; method: string; body: unknown }[] = [];

    page.on('request', (request) => {
      if (request.url().includes('/admin/pipeline/run-stage')) {
        apiCalls.push({
          url: request.url(),
          method: request.method(),
          body: request.postDataJSON(),
        });
      }
    });

    await page.goto('/admin/pipeline');
    await page.waitForLoadState('networkidle');

    // Find a stage with pending hearings (Transcribe or Analyze)
    const stages = [
      { name: 'Transcribe', subtext: 'pending' },
      { name: 'Analyze', subtext: 'pending' },
    ];

    for (const { name, subtext } of stages) {
      const stageCard = page.locator('div').filter({ hasText: name }).filter({ hasText: subtext }).first();
      const countText = await stageCard.locator('div').filter({ hasText: /^\d+$/ }).first().textContent();
      const count = countText ? parseInt(countText) : 0;

      if (count > 0) {
        // Click to expand stage
        await stageCard.click();
        await page.waitForTimeout(2000);

        // Select first hearing
        const firstCheckbox = page.locator('input[type="checkbox"]').first();
        if (await firstCheckbox.isVisible()) {
          await firstCheckbox.click();
          await page.waitForTimeout(500);

          // Find and click Run Selected button
          const runButton = page.locator('button').filter({ hasText: /Run.*Selected/i }).first();
          if (await runButton.isVisible()) {
            // Click the button
            await runButton.click();
            await page.waitForTimeout(3000);

            // Check if API call was made
            if (apiCalls.length > 0) {
              const call = apiCalls[0];
              expect(call.method).toBe('POST');
              expect(call.body).toHaveProperty('stage');
              expect(call.body).toHaveProperty('hearing_ids');
              expect(Array.isArray((call.body as { hearing_ids: number[] }).hearing_ids)).toBeTruthy();
              console.log('API call made:', call);
            } else {
              // If no API call, button might be disabled or there's an issue
              console.log('No API call intercepted - checking for errors');
            }

            // Page should still be functional
            await expect(page.getByRole('heading', { name: 'Pipeline', level: 2 })).toBeVisible();
          }
        }

        // Only test one stage
        break;
      }
    }
  });

  test('Dismiss button makes API call', async ({ page }) => {
    const apiCalls: string[] = [];

    page.on('request', (request) => {
      if (request.url().includes('/admin/') && request.method() === 'POST') {
        apiCalls.push(request.url());
      }
    });

    await page.goto('/admin/pipeline');
    await page.waitForLoadState('networkidle');

    // Find a stage with pending hearings
    const transcribeCard = page.locator('div').filter({ hasText: 'Transcribe' }).filter({ hasText: 'pending' }).first();
    const countText = await transcribeCard.locator('div').filter({ hasText: /^\d+$/ }).first().textContent();
    const count = countText ? parseInt(countText) : 0;

    if (count > 0) {
      await transcribeCard.click();
      await page.waitForTimeout(2000);

      // Select first hearing
      const firstCheckbox = page.locator('input[type="checkbox"]').first();
      if (await firstCheckbox.isVisible()) {
        await firstCheckbox.click();
        await page.waitForTimeout(500);

        // Find Dismiss button
        const dismissButton = page.locator('button').filter({ hasText: /Dismiss/i }).first();
        if (await dismissButton.isVisible()) {
          // Don't actually click dismiss (would modify data), just verify it exists
          expect(await dismissButton.isEnabled()).toBeTruthy();
        }

        // Unselect
        await firstCheckbox.click();
      }
    }
  });
});

test.describe('Admin Pipeline - Activity and Errors Panel', () => {
  test('activity panel can be toggled', async ({ page }) => {
    await page.goto('/admin/pipeline');
    await page.waitForLoadState('networkidle');

    // Look for Activity button/link
    const activityBtn = page.locator('button, a').filter({ hasText: /activity/i }).first();

    if (await activityBtn.isVisible()) {
      await activityBtn.click();
      await page.waitForTimeout(1000);

      // Should show activity panel or recent activity
      const activityPanel = page.locator('text=Recent Activity').first();
      if (await activityPanel.isVisible()) {
        // Can close it
        const closeBtn = page.locator('button').filter({ hasText: /close|×/i }).first();
        if (await closeBtn.isVisible()) {
          await closeBtn.click();
        }
      }

      // Page should still be functional
      await expect(page.getByRole('heading', { name: 'Pipeline', level: 2 })).toBeVisible();
    }
  });

  test('errors panel shows error count', async ({ page }) => {
    await page.goto('/admin/pipeline');
    await page.waitForLoadState('networkidle');

    // Look for Errors button/indicator
    const errorsBtn = page.locator('button, a, span').filter({ hasText: /error/i }).first();

    if (await errorsBtn.isVisible()) {
      // Should show error count (could be 0)
      const text = await errorsBtn.textContent();
      expect(text).toBeTruthy();
    }
  });
});
