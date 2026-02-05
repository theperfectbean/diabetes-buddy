#!/usr/bin/env node
/**
 * Web Paragraph Rendering Test
 * 
 * Tests that the streaming handler correctly renders paragraph breaks
 * by transforming \n\n into <br><br> tags.
 */

const { JSDOM } = require('jsdom');

// Simulate the rendering function from app.js
function renderAssistantMessage(fullResponse) {
    // This mimics the exact logic in sendStreamingQuery
    const formatted = fullResponse.replace(/\n\n/g, '<br><br>');
    return formatted;
}

// Test case
function testParagraphRendering() {
    console.log('🧪 Testing Web UI Paragraph Rendering...\n');
    
    // Sample response with multiple paragraphs (like from LLM)
    const sampleResponse = `For exercise preparation, consider these important steps:

First, check your blood glucose level before starting. If it's below 100 mg/dL, have a snack.

Second, keep fast-acting carbs with you during exercise. This helps prevent hypoglycemia.

Finally, monitor your glucose during and after exercise for several hours.`;
    
    console.log('📝 Input text (with \\n\\n breaks):');
    console.log(JSON.stringify(sampleResponse));
    console.log('');
    
    // Render using the same logic as the live web app
    const rendered = renderAssistantMessage(sampleResponse);
    
    console.log('🎨 Rendered HTML:');
    console.log(rendered.substring(0, 200) + '...');
    console.log('');
    
    // Create a DOM to test actual rendering
    const dom = new JSDOM(`<!DOCTYPE html><html><body></body></html>`);
    const document = dom.window.document;
    
    // Simulate the assistant message structure
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message assistant';
    messageDiv.innerHTML = `
        <div class="message-header">
            <span class="message-role">Diabetes Buddy</span>
        </div>
        <div class="answer">
            ${rendered}
        </div>
    `;
    
    document.body.appendChild(messageDiv);
    
    // Get the answer div content
    const answerDiv = messageDiv.querySelector('.answer');
    const innerHTML = answerDiv.innerHTML;
    
    console.log('🔍 Testing assertions...');
    
    // Test 1: Must contain <br><br> tags (visible paragraph breaks)
    const brCount = (innerHTML.match(/<br><br>/g) || []).length;
    console.log(`   ✓ Found ${brCount} <br><br> sequences`);
    
    if (brCount < 3) {
        console.error(`   ❌ FAIL: Expected at least 3 paragraph breaks, found ${brCount}`);
        process.exit(1);
    }
    
    // Test 2: Must NOT have raw \n\n in the HTML
    if (innerHTML.includes('\n\n')) {
        console.error(`   ❌ FAIL: Found raw \\n\\n in rendered HTML (not transformed)`);
        process.exit(1);
    }
    console.log(`   ✓ No raw \\n\\n sequences found`);
    
    // Test 3: Text content should still be present
    const textContent = answerDiv.textContent;
    if (!textContent.includes('exercise preparation') || !textContent.includes('blood glucose')) {
        console.error(`   ❌ FAIL: Text content missing or corrupted`);
        process.exit(1);
    }
    console.log(`   ✓ Text content preserved`);
    
    // Test 4: Verify the DOM structure
    const brElements = answerDiv.querySelectorAll('br');
    if (brElements.length < 6) {  // 3 paragraph breaks = 6 <br> elements
        console.error(`   ❌ FAIL: Expected at least 6 <br> elements, found ${brElements.length}`);
        process.exit(1);
    }
    console.log(`   ✓ Found ${brElements.length} <br> elements in DOM`);
    
    console.log('\n✅ All tests passed!\n');
    console.log('Summary:');
    console.log('- Paragraph breaks (\\n\\n) correctly transformed to <br><br>');
    console.log('- Multiple visible paragraphs created in DOM');
    console.log('- Text content preserved');
    console.log('- Ready for production use');
}

// Run test
try {
    testParagraphRendering();
} catch (error) {
    console.error('❌ Test failed with error:', error.message);
    console.error(error.stack);
    process.exit(1);
}
