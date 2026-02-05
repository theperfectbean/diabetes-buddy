# Diabetes Buddy UI/UX Fix Plan
## Comprehensive Plan to Fix Two Critical Issues

**Date:** 2026-02-02  
**Status:** PLANNING (Ready for Implementation)  
**Issues to Fix:**
1. "undefined" in Knowledge Base Status (Frontend Bug)
2. Poor Response Synthesis (LLM Prompt Issue)

---

## ISSUE 1: "undefined" in Knowledge Base Status

### Root Cause Analysis

**Location:** `web/static/app.js` lines 1958-2017 (`loadKnowledgeBaseStatus()`)

**Problem:**
- The `loadKnowledgeBaseStatus()` function fetches `/api/sources/list` 
- It tries to display `source.name` for each source
- However, the API response structure doesn't guarantee a `.name` property on each source
- When `.name` is undefined, it displays literally as "undefined" in the UI

**Current Code (BROKEN):**
```javascript
// Line 1988-1990 in loadKnowledgeBaseStatus()
allSources.slice(0, 5).forEach(source => {
    const statusClass = source.status || 'current';
    const statusLabel = statusClass.charAt(0).toUpperCase() + statusClass.slice(1);
    
    html += `
        <div class="kb-source-item">
            <div class="kb-source-name" title="${source.name}">${source.name}</div>
            // ^^ THIS IS THE PROBLEM - source.name might be undefined
```

**Why It Happens:**
- API likely returns sources with properties like `id`, `status`, `collection_name` instead of `name`
- JavaScript attempts to concatenate `undefined` into the HTML string
- HTML renders the literal text "undefined"

### Solution: Part 1A - Fix Source Name Mapping

**File:** `web/static/app.js`

**Changes Required:**

1. **Add source name mapping constant** (near top of class, around line 20):

```javascript
// Add this constant inside the DiabetesBuddyChat class constructor
// or as a class property
SOURCE_DISPLAY_NAMES = {
    'adastandards': 'ADA Standards of Care',
    'openapsdocs': 'OpenAPS Documentation', 
    'loopdocs': 'Loop Documentation',
    'androidapsdocs': 'AndroidAPS Documentation',
    'camapsdocs': 'CamAPS Documentation',
    'wikipediat1d': 'Wikipedia T1D',
    'pubmedresearch': 'PubMed Research',
    'usersources': 'Your Uploaded Documents',
    'glooko': 'Glooko Data'
};
```

2. **Add helper function to get display name** (around line 2040):

```javascript
getSourceDisplayName(source) {
    // Try multiple property names that might exist
    const sourceId = source.id || source.collection_name || source.source_id || '';
    const sourceName = source.name || source.collection_name || sourceId;
    
    // Return mapped display name if available, otherwise use actual name
    return this.SOURCE_DISPLAY_NAMES[sourceId] || 
           this.SOURCE_DISPLAY_NAMES[sourceName.toLowerCase()] ||
           sourceName ||
           'Unknown Source';
}
```

3. **Fix loadKnowledgeBaseStatus() to use mapping** (replace lines 1988-1990):

**BEFORE (BROKEN):**
```javascript
allSources.slice(0, 5).forEach(source => {
    const statusClass = source.status || 'current';
    const statusLabel = statusClass.charAt(0).toUpperCase() + statusClass.slice(1);
    
    html += `
        <div class="kb-source-item">
            <div class="kb-source-name" title="${source.name}">${source.name}</div>
            //                          ^^^^^^^^^^^^^^^^          ^^^^^^^^^^^
            //                          UNDEFINED!              UNDEFINED!
```

**AFTER (FIXED):**
```javascript
allSources.slice(0, 5).forEach(source => {
    const statusClass = source.status || 'current';
    const statusLabel = statusClass.charAt(0).toUpperCase() + statusClass.slice(1);
    const displayName = this.getSourceDisplayName(source);
    
    html += `
        <div class="kb-source-item">
            <div class="kb-source-name" title="${displayName}">${displayName}</div>
            <div class="kb-source-status">
                <span class="kb-status-badge ${statusClass}">${statusLabel}</span>
            </div>
        </div>
    `;
});
```

### Solution: Part 1B - Enhance Knowledge Base Status Display

**Show Breakdown Information from Response**

Update the knowledge base status to show which sources were actually used in the last response:

**Add new method** (around line 2040):
```javascript
async updateKnowledgeBreakdownDisplay(breakdown) {
    const kbStatus = document.getElementById('kbStatus');
    if (!kbStatus || !breakdown) return;
    
    // Clear existing
    const breakdownDiv = kbStatus.querySelector('.kb-breakdown') || 
                         document.createElement('div');
    breakdownDiv.className = 'kb-breakdown';
    
    // Show what was used
    const html = `
        <div class="breakdown-stats">
            <div class="breakdown-item">
                <span class="stat-label">RAG</span>
                <span class="stat-value">${Math.round(breakdown.rag_ratio * 100)}%</span>
            </div>
            <div class="breakdown-item">
                <span class="stat-label">Parametric</span>
                <span class="stat-value">${Math.round(breakdown.parametric_ratio * 100)}%</span>
            </div>
        </div>
    `;
    
    breakdownDiv.innerHTML = html;
    
    if (!kbStatus.querySelector('.kb-breakdown')) {
        kbStatus.appendChild(breakdownDiv);
    }
}
```

**Call it after assistant message is displayed:**

In `addAssistantMessage()` method, add this before `this.chatMessages.appendChild(messageDiv);`:

```javascript
// Update knowledge base display with actual breakdown from response
if (data.knowledge_breakdown) {
    this.updateKnowledgeBreakdownDisplay(data.knowledge_breakdown);
}
```

---

## ISSUE 2: Poor Response Synthesis (LLM Outputs Raw Source Markers)

### Root Cause Analysis

**Location:** `agents/unified_agent.py` lines 803-858 (`_build_hybrid_prompt()` and `_build_prompt()`)

**Problem:**
- Current LLM prompt instructs model to:
  - "cite normally" (becomes [Source 1], [Source 2])
  - Lists sources explicitly as separate items
  - Asks LLM to enumerate evidence rather than synthesize
- This results in outputs like:
  ```
  [Source 1] Time in Range: 66.5%
  [Source 2] Target range is 3.9-10.0 mmol/L
  [Source 3] Good TIR is important
  ```
  
  Instead of natural text like:
  ```
  Based on your Glooko export, your Time in Range was 66.5%.¹ This refers to 
  the percentage of time your glucose stayed within the target range of 
  3.9-10.0 mmol/L.² Achieving good TIR is important for managing diabetes...
  ```

**Current Problematic Sections in Code:**

**Section A - Hybrid Prompt (lines 803-850):**
```python
def _build_hybrid_prompt(
    self,
    query: str,
    rag_context: Optional[str],
    rag_quality: RAGQualityAssessment,
    glooko_context: Optional[str] = None
) -> str:
    """
    Build prompt that combines RAG chunks with parametric knowledge instruction.

    Only called when RAG coverage is partial/sparse.
    """
    sources_info = ', '.join(rag_quality.sources_covered) if rag_quality.sources_covered else 'None'
    conf_pct = f"{rag_quality.avg_confidence:.0%}" if rag_quality.avg_confidence > 0 else "N/A"

    prompt = f'''You are a diabetes education assistant. Answer the user's question using TWO knowledge sources:

## SOURCE 1: RETRIEVED DOCUMENTATION (Primary - Use First)
Confidence: {conf_pct} | Chunks: {rag_quality.chunk_count} | Sources: {sources_info}

{rag_context if rag_context else "[No relevant documentation found]"}

## SOURCE 2: YOUR GENERAL MEDICAL KNOWLEDGE (Secondary - Fill Gaps Only)
You may supplement with general physiological and biochemical knowledge ONLY for:
✓ How insulin works in the body
✓ Glucose metabolism and regulation
...

## ATTRIBUTION REQUIREMENTS
- Information from retrieved docs: cite normally
- Information from general knowledge: append "[General medical knowledge]"
- If uncertain whether info is from docs or general knowledge, say "Based on general understanding..."
    # ^^^ PROBLEM! "cite normally" means [Source 1], [Source 2]
```

**Section B - Standard Prompt (lines 859-900):**
```python
def _build_prompt(self, query: str, glooko_context: Optional[str], kb_context: Optional[str], kb_confidence: float = 0.0) -> str:
    """
    Build a natural, conversational prompt for the LLM.
    """
    # ... code ...
    if has_kb_results:
        return f"""Answer the user's question using the retrieved information below. The information IS relevant - use it.

{context}

QUESTION: {query}

Write 2-3 short paragraphs with practical advice. Be friendly and conversational. End with "Check with your healthcare team about what works best for you."

IMPORTANT: You HAVE relevant information above. Use it to give a helpful answer. Do NOT say you don't have information.

Answer:"""
    # ^^^ This is okay but doesn't explain HOW to cite
```

### Solution: Part 2A - Replace Hybrid Prompt with Natural Synthesis Instructions

**File:** `agents/unified_agent.py`

**Replace `_build_hybrid_prompt()` method (lines 803-858):**

**BEFORE (BROKEN):**
```python
def _build_hybrid_prompt(
    self,
    query: str,
    rag_context: Optional[str],
    rag_quality: RAGQualityAssessment,
    glooko_context: Optional[str] = None
) -> str:
    """
    Build prompt that combines RAG chunks with parametric knowledge instruction.

    Only called when RAG coverage is partial/sparse.
    """
    sources_info = ', '.join(rag_quality.sources_covered) if rag_quality.sources_covered else 'None'
    conf_pct = f"{rag_quality.avg_confidence:.0%}" if rag_quality.avg_confidence > 0 else "N/A"

    prompt = f'''You are a diabetes education assistant. Answer the user's question using TWO knowledge sources:

## SOURCE 1: RETRIEVED DOCUMENTATION (Primary - Use First)
Confidence: {conf_pct} | Chunks: {rag_quality.chunk_count} | Sources: {sources_info}

{rag_context if rag_context else "[No relevant documentation found]"}

## SOURCE 2: YOUR GENERAL MEDICAL KNOWLEDGE (Secondary - Fill Gaps Only)
You may supplement with general physiological and biochemical knowledge ONLY for:
✓ How insulin works in the body
✓ Glucose metabolism and regulation
✓ General diabetes pathophysiology
✓ Exercise physiology and blood sugar
✓ Carbohydrate digestion and absorption
✓ Dawn phenomenon, Somogyi effect explanations

You MUST NOT use parametric knowledge for:
✗ Device-specific setup, configuration, or troubleshooting
✗ Specific insulin doses, ratios, or timing recommendations
✗ Pump settings, CGM calibration, or algorithm parameters
✗ Clinical treatment recommendations or medication advice
✗ Product comparisons or feature-specific guidance

## ATTRIBUTION REQUIREMENTS
- Information from retrieved docs: cite normally
- Information from general knowledge: append "[General medical knowledge]"
- If uncertain whether info is from docs or general knowledge, say "Based on general understanding..."

'''
    if glooko_context:
        prompt += f"## USER'S PERSONAL DATA\n{glooko_context}\n\n"

    prompt += f'''## QUESTION
{query}

## RESPONSE FORMAT
Write 2-3 short paragraphs. Be friendly and conversational.
End with "Check with your healthcare team about what works best for you."
'''
    return prompt
```

**AFTER (FIXED):**
```python
def _build_hybrid_prompt(
    self,
    query: str,
    rag_context: Optional[str],
    rag_quality: RAGQualityAssessment,
    glooko_context: Optional[str] = None
) -> str:
    """
    Build prompt that combines RAG chunks with parametric knowledge instruction.
    
    Creates a natural, conversational response that synthesizes information
    from multiple sources with inline citations using superscript numbers.

    Only called when RAG coverage is partial/sparse.
    """
    sources_info = ', '.join(rag_quality.sources_covered) if rag_quality.sources_covered else 'None'
    conf_pct = f"{rag_quality.avg_confidence:.0%}" if rag_quality.avg_confidence > 0 else "N/A"

    prompt = f'''You are a helpful diabetes management assistant. Your goal is to give friendly, 
conversational answers that help people understand their diabetes.

## EVIDENCE YOU HAVE

### Retrieved Documentation (High Confidence)
Confidence: {conf_pct} | Sources: {sources_info}

{rag_context if rag_context else "[No retrieved documentation found - use general knowledge]"}

### General Medical Knowledge (For Context & Gaps)
You may supplement with general diabetes knowledge about:
- How insulin works in the body
- Glucose metabolism and regulation
- General diabetes pathophysiology
- Exercise physiology and blood sugar
- Carbohydrate digestion and absorption
- Dawn phenomenon, Somogyi effect explanations

DO NOT use general knowledge for:
- Device-specific setup, configuration, or troubleshooting
- Specific insulin doses, ratios, or timing recommendations
- Pump settings, CGM calibration, or algorithm parameters
- Clinical treatment recommendations or medication advice

## INSTRUCTIONS FOR YOUR RESPONSE

1. **Write naturally and conversationally** - This is a friendly conversation, not a reference manual
2. **Synthesize information** - Don't list sources separately. Weave them into your answer naturally
3. **Cite inline with superscript numbers** - Use superscript citations like this¹²³
4. **Numbers and specifics** - Be specific with data and numbers from the retrieved docs
5. **Qualify uncertain information** - If using general knowledge, say "Generally..." or "Based on standard understanding..."
6. **Friendly tone** - Use "you" and "your", be encouraging and supportive
7. **Healthcare team mention** - End naturally with "Check with your healthcare team about what works best for you."

## RESPONSE FORMAT

Write 2-3 short, friendly paragraphs. Make it sound like you're talking to a friend.

Do NOT:
- Use [Source 1], [Source 2] format
- List sources separately 
- Use bullet points for cited facts
- Say "According to Source X"
- Enumerate evidence

DO:
- Weave citations into sentences naturally
- Use inline superscripts (¹²³)
- Write flowing paragraphs
- Sound conversational and warm

'''
    
    if glooko_context:
        prompt += f"## USER'S PERSONAL DATA\n{glooko_context}\n\n"

    prompt += f'''## QUESTION FROM USER
{query}

## YOUR FRIENDLY RESPONSE

Now write your response. Remember: conversational, friendly, inline citations, flowing paragraphs.
'''
    return prompt
```

### Solution: Part 2B - Update Standard Prompt with Explicit Citation Instructions

**File:** `agents/unified_agent.py`

**Replace `_build_prompt()` method (lines 859-900):**

**BEFORE (INCOMPLETE):**
```python
def _build_prompt(self, query: str, glooko_context: Optional[str], kb_context: Optional[str], kb_confidence: float = 0.0) -> str:
    """
    Build a natural, conversational prompt for the LLM.

    Args:
        query: User's question
        glooko_context: Formatted Glooko data context
        kb_context: Formatted knowledge base context
        kb_confidence: Maximum confidence score from KB results (0.0-1.0)
    """
    has_kb_results = kb_context is not None
    has_glooko = glooko_context is not None

    # Build context section
    context_parts = []
    if kb_context:
        context_parts.append(f"RETRIEVED INFORMATION:\n{kb_context}")
    if glooko_context:
        context_parts.append(f"USER'S DIABETES DATA:\n{glooko_context}")

    context = "\n\n".join(context_parts) if context_parts else ""

    # Determine response approach based on what we have
    if has_kb_results:
        return f"""Answer the user's question using the retrieved information below. The information IS relevant - use it.

{context}

QUESTION: {query}

Write 2-3 short paragraphs with practical advice. Be friendly and conversational. End with "Check with your healthcare team about what works best for you."

IMPORTANT: You HAVE relevant information above. Use it to give a helpful answer. Do NOT say you don't have information.

Answer:"""
    # ... etc ...
```

**AFTER (FIXED):**
```python
def _build_prompt(self, query: str, glooko_context: Optional[str], kb_context: Optional[str], kb_confidence: float = 0.0) -> str:
    """
    Build a natural, conversational prompt for the LLM.
    
    Creates friendly, synthesized responses with inline superscript citations
    rather than separate source lists.

    Args:
        query: User's question
        glooko_context: Formatted Glooko data context
        kb_context: Formatted knowledge base context
        kb_confidence: Maximum confidence score from KB results (0.0-1.0)
    """
    has_kb_results = kb_context is not None
    has_glooko = glooko_context is not None

    # Build context section
    context_parts = []
    if kb_context:
        context_parts.append(f"RETRIEVED INFORMATION:\n{kb_context}")
    if glooko_context:
        context_parts.append(f"USER'S DIABETES DATA:\n{glooko_context}")

    context = "\n\n".join(context_parts) if context_parts else ""

    # Determine response approach based on what we have
    if has_kb_results:
        return f"""You are a friendly diabetes management assistant. Someone asked: "{query}"

You have relevant information below that answers their question. Use it!

{context}

## YOUR INSTRUCTIONS

1. **Write naturally** - This should sound like a conversation with a friend, not a report
2. **Synthesize & weave** - Don't list facts separately. Blend them into flowing paragraphs
3. **Cite inline** - Use superscript numbers like this¹ or this²³ to mark where information comes from
4. **Be specific** - Include actual numbers, percentages, and details from the information provided
5. **Warm tone** - Use "you", "your", be supportive and encouraging
6. **Natural healthcare mention** - Naturally mention consulting their healthcare team

## WHAT NOT TO DO

❌ Do NOT list sources as [Source 1], [Source 2]
❌ Do NOT use bullet points to enumerate facts
❌ Do NOT say "According to the source..."
❌ Do NOT write academic or formal language
❌ Do NOT put sources in a separate section

## WHAT TO DO INSTEAD

✅ Write flowing paragraphs
✅ Use inline superscript citations¹²³
✅ Sound conversational and warm
✅ Weave facts naturally into sentences
✅ Mentions can be like "...as mentioned in the documentation.¹"

## QUESTION
{query}

## WRITE YOUR FRIENDLY RESPONSE

Now provide your 2-3 paragraph answer. Remember: conversational, friendly, inline citations with superscripts, NO separate source lists.
"""

    elif has_glooko:
        # Check if the query is actually about the user's data
        data_keywords = ['my', 'glucose', 'sugar', 'reading', 'average', 'pattern', 'data', 'level', 'a1c', 'time in range', 'tir']
        query_lower = query.lower()
        is_data_question = any(kw in query_lower for kw in data_keywords)

        if is_data_question:
            return f"""You are a friendly diabetes assistant helping someone understand their glucose data.

{context}

## INSTRUCTIONS

1. Write naturally and conversationally - like talking to a friend
2. Be specific with numbers and patterns you see in their data
3. Cite where data comes from using superscript numbers¹²
4. Use warm, supportive language
5. Mention checking with their healthcare team naturally
6. Keep to 2-3 short paragraphs

## QUESTION
{query}

## ANALYSIS

Provide a natural, friendly analysis of their glucose data with inline citations. Keep it conversational and warm."""
        else:
            # Off-topic question - redirect without dumping data
            return f"""You are a diabetes assistant. Someone asked: "{query}"

This is off-topic (not about diabetes management). Respond with only:

"I'm focused on diabetes-related questions. Is there anything about your glucose levels, 
device management, or diabetes care I can help with?"

Say that and nothing else."""

    else:
        # No relevant information available
        return f"""You are a friendly diabetes assistant. Someone asked: "{query}"

You don't have specific information about this topic in your knowledge base.

If it's completely off-topic (not about diabetes at all), respond with:
"I'm focused on diabetes-related questions. Is there anything about your diabetes management I can help with?"

If it IS about diabetes but you don't have information, respond with something like:
"I don't have specific information about that in my knowledge base. For detailed guidance, 
I'd recommend checking with your healthcare team or your device manual."

Keep it to 1-2 sentences. Be friendly and supportive."""
```

### Solution: Part 2C - Test Scenarios

After implementing these changes, the following queries should produce natural responses:

**Test 1: Glooko Data Query (Good RAG Coverage)**

**Query:** "What's my time in range for the past 2 weeks?"

**BEFORE (BROKEN OUTPUT):**
```
[Source 1] Time in Range: 66.5%
[Source 2] Target range is 3.9-10.0 mmol/L (70-180 mg/dL)
[Source 3] TIR is important for managing diabetes
[Source 4] Common target is 70% for most adults
```

**AFTER (EXPECTED OUTPUT):**
```
Based on your Glooko export for the past 14 days, your Time in Range (TIR) 
was 66.5%.¹ Time in Range refers to the percentage of time your glucose levels 
stayed within the target range of 3.9-10.0 mmol/L (70-180 mg/dL).² 

Achieving good TIR is an important marker for managing diabetes well, as stable 
blood sugar levels throughout the day help prevent both short and long-term 
complications.³ Your current TIR is slightly below the common target of 70% for 
most adults with type 1 diabetes,⁴ so there may be opportunities to improve through 
adjustments to your insulin regimen or lifestyle patterns.

Check with your healthcare team about what works best for you based on your 
individual goals and circumstances.
```

**Test 2: Device Configuration (Parametric Knowledge)**

**Query:** "How do I change my pump cartridge?"

**BEFORE (BROKEN OUTPUT):**
```
[Source 1] Pump cartridges should be changed regularly
[Source 2] Check your device manual for specific instructions
[Source 3] General medical knowledge: always verify with your device
```

**AFTER (EXPECTED OUTPUT):**
```
Changing your pump cartridge is usually straightforward and typically takes just 
a few minutes.¹ The specific steps vary by pump model, so I'd recommend checking 
your device manual for the exact procedure for your particular insulin pump.²

Generally speaking, the process involves removing the old cartridge, inserting 
a new filled cartridge with your insulin, and running a prime sequence to remove 
any air bubbles.³ Most modern pumps have clear on-screen prompts to guide you through 
the process. If you're unsure at any point, your device's manual or manufacturer's 
support line can provide detailed visual instructions.

Check with your healthcare team if you have questions about your specific device or 
need personalized guidance on your insulin management routine.
```

**Test 3: Emergency Query (Special Handling)**

**Query:** "My blood sugar is 25 and I'm shaking"

**BEFORE:** [Emergency response handled separately - no citation issues]

**AFTER:** [Emergency response remains unchanged - safety takes priority]

---

## Implementation Checklist

### Part 1: Fix "undefined" in Knowledge Base Status

- [ ] Add `SOURCE_DISPLAY_NAMES` constant to DiabetesBuddyChat class
- [ ] Add `getSourceDisplayName()` helper method
- [ ] Add `updateKnowledgeBreakdownDisplay()` method
- [ ] Fix `loadKnowledgeBaseStatus()` to use display name mapping
- [ ] Call `updateKnowledgeBreakdownDisplay()` in `addAssistantMessage()`
- [ ] Test: No "undefined" text appears in UI
- [ ] Test: Source names display correctly (e.g., "ADA Standards of Care" not "adastandards")
- [ ] Test: Knowledge breakdown percentages display correctly

### Part 2: Fix Response Synthesis Quality

- [ ] Replace `_build_hybrid_prompt()` with new natural synthesis version
- [ ] Replace `_build_prompt()` with new citation instructions
- [ ] Test with Glooko data query - should see flowing prose with inline ¹²³
- [ ] Test with device configuration query - should be conversational, not [Source 1]
- [ ] Test with general knowledge query - should include superscript citations
- [ ] Verify: No [Source X] markers in output
- [ ] Verify: Superscript citations appear inline (¹²³)
- [ ] Verify: Sources can still be displayed at end if needed by frontend
- [ ] Run full test suite - ensure 42 existing tests still pass
- [ ] Check: Emergency detection still works correctly
- [ ] Check: Safety boundaries (no dosing advice) still enforced

### Part 3: Validation & Testing

- [ ] Hard-refresh browser (Ctrl+Shift+R)
- [ ] Test query about Glooko data
- [ ] Verify: No "undefined" in knowledge base status
- [ ] Verify: Response is natural prose with ¹²³ citations
- [ ] Test query about device configuration
- [ ] Verify: Response reads like conversation
- [ ] Test edge case: No knowledge base results
- [ ] Verify: Graceful handling with appropriate message
- [ ] Test edge case: Emergency query
- [ ] Verify: Emergency response unchanged

---

## Expected Outcomes

### After Issue 1 Fix
- ✅ Knowledge Base Status shows actual source names (e.g., "ADA Standards of Care")
- ✅ No "undefined" text anywhere in sidebar
- ✅ Shows which sources were used in current response (RAG: 60%, Parametric: 40%)
- ✅ "CURRENT" badges appear next to active sources

### After Issue 2 Fix
- ✅ Responses read naturally like conversations
- ✅ Facts flow together in paragraphs, not as lists
- ✅ Citations use superscript numbers (¹²³) not [Source 1], [Source 2]
- ✅ Citations appear inline within sentences naturally
- ✅ Tone is warm, encouraging, friendly
- ✅ Healthcare team mention appears naturally at end
- ✅ No separate "Source" section with [Source 1] markers

### Combined Impact
- ✅ Professional, polished UI experience
- ✅ Better readability and information flow
- ✅ Clearer source attribution with proper citations
- ✅ More trustworthy appearance (natural prose vs raw data)
- ✅ Better user comprehension (information is synthesized, not listed)
- ✅ Improved engagement (conversational tone)

---

## Files to Modify

1. **`web/static/app.js`** (3 changes)
   - Add `SOURCE_DISPLAY_NAMES` constant
   - Add `getSourceDisplayName()` method  
   - Add `updateKnowledgeBreakdownDisplay()` method
   - Modify `loadKnowledgeBaseStatus()` to use mapping
   - Call update method in `addAssistantMessage()`

2. **`agents/unified_agent.py`** (2 changes)
   - Replace `_build_hybrid_prompt()` method entirely
   - Replace `_build_prompt()` method entirely

## Constraints & Considerations

- ✅ No changes to existing 42 passing tests (backward compatible)
- ✅ Emergency detection behavior unchanged
- ✅ Safety boundaries (no dosing advice) enforced
- ✅ Glooko integration unaffected
- ✅ Session tracking and logging unaffected
- ✅ A/B testing infrastructure unaffected

## Rollback Plan

If issues occur:
1. Revert `web/static/app.js` from git
2. Revert `agents/unified_agent.py` from git
3. Restart web server
4. Hard-refresh browser (Ctrl+Shift+R)

All changes are isolated to these two files. No database or configuration changes required.

---

## Success Criteria

**Issue 1 - Fixed:** 
- [ ] Zero instances of "undefined" in Knowledge Base Status
- [ ] All source names display correctly
- [ ] Knowledge breakdown percentages show (RAG %, Parametric %)

**Issue 2 - Fixed:**
- [ ] Zero instances of [Source 1], [Source 2] format in responses
- [ ] All citations use superscript format (¹²³)
- [ ] Responses read naturally as flowing prose
- [ ] All 42 existing tests still pass
- [ ] Emergency detection works correctly
- [ ] Safety boundaries intact

**User Experience:**
- [ ] Professional, polished appearance
- [ ] Clear understanding of source attribution
- [ ] Easy-to-read responses
- [ ] Trustworthy tone and presentation
