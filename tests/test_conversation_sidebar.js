#!/usr/bin/env node
/**
 * Conversation Sidebar Visibility Test
 * 
 * Tests that the conversation sidebar is visible even when there are no conversations.
 */

const { JSDOM } = require('jsdom');
const fs = require('fs');
const path = require('path');

// Read the actual HTML file
const htmlPath = path.join(__dirname, '..', 'web', 'index.html');
const htmlContent = fs.readFileSync(htmlPath, 'utf8');

// Read the actual CSS file
const cssPath = path.join(__dirname, '..', 'web', 'static', 'styles.css');
const cssContent = fs.readFileSync(cssPath, 'utf8');

// Read the actual JS file
const jsPath = path.join(__dirname, '..', 'web', 'static', 'app.js');
const jsContent = fs.readFileSync(jsPath, 'utf8');

console.log('🧪 Testing Conversation Sidebar Visibility...\n');

// Test 1: Check HTML structure
console.log('Test 1: HTML Structure');
console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');

const dom = new JSDOM(htmlContent);
const document = dom.window.document;

const sidebar = document.querySelector('.conversation-sidebar');
const conversationList = document.getElementById('conversationList');
const newConversationBtn = document.getElementById('newConversationBtn');

if (sidebar) {
    console.log('✅ Sidebar element exists');
} else {
    console.log('❌ Sidebar element NOT FOUND');
    process.exit(1);
}

if (conversationList) {
    console.log('✅ Conversation list container exists');
} else {
    console.log('❌ Conversation list container NOT FOUND');
    process.exit(1);
}

if (newConversationBtn) {
    console.log('✅ New conversation button exists');
} else {
    console.log('❌ New conversation button NOT FOUND');
    process.exit(1);
}

console.log('');

// Test 2: Check CSS for visibility
console.log('Test 2: CSS Visibility');
console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');

if (cssContent.includes('.conversation-sidebar')) {
    console.log('✅ Sidebar CSS rules exist');
} else {
    console.log('❌ Sidebar CSS rules NOT FOUND');
    process.exit(1);
}

// Check for any display:none rules that would hide the sidebar by default
const sidebarCssMatch = cssContent.match(/\.conversation-sidebar\s*{[^}]*}/);
if (sidebarCssMatch && sidebarCssMatch[0].includes('display: none')) {
    console.log('❌ Sidebar has display:none in CSS');
    process.exit(1);
} else {
    console.log('✅ Sidebar is not hidden by default CSS');
}

if (cssContent.includes('.empty-state')) {
    console.log('✅ Empty state styling exists');
} else {
    console.log('⚠️  Empty state styling not found (optional)');
}

console.log('');

// Test 3: Check JavaScript functions
console.log('Test 3: JavaScript Functions');
console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');

const requiredFunctions = [
    'loadConversationHistory',
    'renderConversationList',
    'loadConversation',
    'deleteConversation',
    'createNewConversation',
    'updateActiveConversation'
];

let allFunctionsExist = true;
requiredFunctions.forEach(funcName => {
    if (jsContent.includes(funcName)) {
        console.log(`✅ ${funcName}() exists`);
    } else {
        console.log(`❌ ${funcName}() NOT FOUND`);
        allFunctionsExist = false;
    }
});

if (!allFunctionsExist) {
    process.exit(1);
}

console.log('');

// Test 4: Check for the bug fix (sidebar should not be hidden when empty)
console.log('Test 4: Empty State Handling');
console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');

// Find the renderConversationList function DEFINITION (not a call to it)
const renderFuncPattern = 'renderConversationList() {';
const renderFuncStart = jsContent.indexOf(renderFuncPattern);
if (renderFuncStart === -1) {
    console.log('❌ Could not find renderConversationList function');
    process.exit(1);
}

// Extract a reasonable chunk of the function (next 2000 characters to be safe)
const funcContent = jsContent.substring(renderFuncStart, renderFuncStart + 2000);

// Check if sidebar is always shown
const hasBlockDisplay = funcContent.includes("sidebar.style.display = 'block'");
const hasNoneDisplay = funcContent.includes("sidebar.style.display = 'none'");

if (hasBlockDisplay) {
    console.log('✅ Sidebar visibility is explicitly set to block');
    
    // Make sure it's not conditionally hidden
    if (hasNoneDisplay) {
        console.log('❌ Sidebar can still be hidden (bug present)');
        process.exit(1);
    } else {
        console.log('✅ Sidebar is always visible (no conditional hiding)');
    }
} else {
    console.log('⚠️  Sidebar visibility handling not found in function');
}

// Check for empty state message
const hasEmptyState = funcContent.includes('empty-state');
const hasEmptyMessage = funcContent.includes('No conversations');

if (hasEmptyState && hasEmptyMessage) {
    console.log('✅ Empty state message is rendered when no conversations exist');
} else {
    console.log(`❌ Empty state incomplete (empty-state: ${hasEmptyState}, message: ${hasEmptyMessage})`);
    console.log('Function excerpt:', funcContent.substring(0, 500));
    process.exit(1);
}

console.log('');

// Summary
console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
console.log('✅ All tests passed!');
console.log('');
console.log('Sidebar will be visible with:');
console.log('  • Empty state message when no conversations');
console.log('  • Conversation list when conversations exist');
console.log('  • New Chat button always available');
