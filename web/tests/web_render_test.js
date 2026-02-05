const { JSDOM } = require('jsdom');
const marked = require('marked');

// Configure marked like in the app
marked.use({ breaks: true, gfm: true, mangle: false, headerIds: false });

// Simulate the formatting function used in streaming
function formatResponse(text) {
    return window.marked ? marked.parse(text) : text.replace(/\n\n/g, '<br><br>');
}

// Test function
function testParagraphRendering() {
    const sampleText = 'This is the first paragraph.\n\nThis is the second paragraph with more content.\n\nAnd this is the third paragraph.';

    // Create a DOM element to simulate .answer
    const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>');
    global.window = dom.window;
    global.document = dom.window.document;
    global.window.marked = marked; // Make marked available on window

    const answerDiv = document.createElement('div');
    answerDiv.className = 'answer';

    // Apply the formatting
    const formatted = formatResponse(sampleText);
    answerDiv.innerHTML = formatted;

    console.log('Sample text:', JSON.stringify(sampleText));
    console.log('Formatted HTML:', formatted);

    // Check if it contains multiple <p> elements or <br><br>
    const hasMultipleP = (answerDiv.innerHTML.match(/<p>/g) || []).length > 1;
    const hasBrBr = answerDiv.innerHTML.includes('<br><br>');

    if (hasMultipleP || hasBrBr) {
        console.log('PASS: Paragraph breaks detected in HTML');
        return true;
    } else {
        console.log('FAIL: No paragraph breaks found in HTML');
        return false;
    }
}

// Run the test
if (testParagraphRendering()) {
    console.log('Test passed!');
    process.exit(0);
} else {
    console.log('Test failed!');
    process.exit(1);
}