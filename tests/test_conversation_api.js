#!/usr/bin/env node
/**
 * Live Conversation Sidebar Test
 * 
 * Tests the conversation sidebar functionality with a running server.
 * Run this after starting the web server with: python -m web.app
 */

const http = require('http');

const BASE_URL = 'http://localhost:8001';

console.log('🧪 Testing Live Conversation Sidebar...\n');
console.log('Server: ' + BASE_URL);
console.log('');

// Helper to make HTTP requests
function makeRequest(options) {
    return new Promise((resolve, reject) => {
        const req = http.request(options, (res) => {
            let data = '';
            res.on('data', chunk => data += chunk);
            res.on('end', () => {
                try {
                    resolve({
                        status: res.statusCode,
                        data: res.headers['content-type']?.includes('application/json') 
                            ? JSON.parse(data) 
                            : data
                    });
                } catch (e) {
                    resolve({ status: res.statusCode, data });
                }
            });
        });
        req.on('error', reject);
        if (options.body) {
            req.write(JSON.stringify(options.body));
        }
        req.end();
    });
}

async function testAPI() {
    console.log('Test 1: Check main page loads');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    
    try {
        const response = await makeRequest({
            hostname: 'localhost',
            port: 8001,
            path: '/',
            method: 'GET'
        });
        
        if (response.status === 200) {
            const html = response.data;
            if (html.includes('conversation-sidebar') && 
                html.includes('conversationList') &&
                html.includes('newConversationBtn')) {
                console.log('✅ Main page loads with sidebar elements');
            } else {
                console.log('❌ Main page missing sidebar elements');
                process.exit(1);
            }
        } else {
            console.log(`❌ Server returned status ${response.status}`);
            process.exit(1);
        }
    } catch (error) {
        console.log('❌ Failed to connect to server');
        console.log('   Make sure the server is running: python -m web.app');
        process.exit(1);
    }
    
    console.log('');
    
    console.log('Test 2: GET /api/conversations (list conversations)');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    
    try {
        const response = await makeRequest({
            hostname: 'localhost',
            port: 8001,
            path: '/api/conversations',
            method: 'GET'
        });
        
        if (response.status === 200) {
            console.log('✅ Conversations API responds');
            console.log(`   Found ${response.data.length} conversation(s)`);
            
            if (Array.isArray(response.data)) {
                response.data.forEach((conv, i) => {
                    console.log(`   ${i + 1}. ${conv.firstQuery || 'No query'} (${conv.messageCount} messages)`);
                });
            }
        } else {
            console.log(`❌ API returned status ${response.status}`);
            process.exit(1);
        }
    } catch (error) {
        console.log('❌ Failed to fetch conversations:', error.message);
        process.exit(1);
    }
    
    console.log('');
    
    console.log('Test 3: POST /api/conversations (create new)');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    
    try {
        const response = await makeRequest({
            hostname: 'localhost',
            port: 8001,
            path: '/api/conversations',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (response.status === 200) {
            console.log('✅ Can create new conversation');
            console.log(`   Created conversation ID: ${response.data.conversationId}`);
            
            // Store for cleanup
            global.testConversationId = response.data.conversationId;
        } else {
            console.log(`❌ API returned status ${response.status}`);
            process.exit(1);
        }
    } catch (error) {
        console.log('❌ Failed to create conversation:', error.message);
        process.exit(1);
    }
    
    console.log('');
    
    console.log('Test 4: GET /api/conversations/{id} (load specific)');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    
    if (global.testConversationId) {
        try {
            const response = await makeRequest({
                hostname: 'localhost',
                port: 8001,
                path: `/api/conversations/${global.testConversationId}`,
                method: 'GET'
            });
            
            if (response.status === 200) {
                console.log('✅ Can load conversation by ID');
                console.log(`   Messages: ${response.data.messages?.length || 0}`);
            } else {
                console.log(`❌ API returned status ${response.status}`);
                process.exit(1);
            }
        } catch (error) {
            console.log('❌ Failed to load conversation:', error.message);
            process.exit(1);
        }
    } else {
        console.log('⚠️  Skipped (no test conversation created)');
    }
    
    console.log('');
    
    console.log('Test 5: DELETE /api/conversations/{id} (cleanup)');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    
    if (global.testConversationId) {
        try {
            const response = await makeRequest({
                hostname: 'localhost',
                port: 8001,
                path: `/api/conversations/${global.testConversationId}`,
                method: 'DELETE'
            });
            
            if (response.status === 200) {
                console.log('✅ Can delete conversation');
            } else {
                console.log(`⚠️  Delete returned status ${response.status}`);
            }
        } catch (error) {
            console.log('⚠️  Failed to delete test conversation:', error.message);
        }
    } else {
        console.log('⚠️  Skipped (no test conversation to delete)');
    }
    
    console.log('');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log('✅ All API tests passed!');
    console.log('');
    console.log('Manual Testing:');
    console.log('1. Open http://localhost:8001 in your browser');
    console.log('2. Check that the left sidebar is visible');
    console.log('3. Send a test message');
    console.log('4. Verify conversation appears in sidebar');
    console.log('5. Refresh page and verify conversation persists');
    console.log('6. Click conversation to reload it');
    console.log('7. Click "New Chat" to start fresh');
    console.log('8. Click delete button (trash icon) to remove conversation');
}

testAPI().catch(error => {
    console.error('Test failed:', error);
    process.exit(1);
});
