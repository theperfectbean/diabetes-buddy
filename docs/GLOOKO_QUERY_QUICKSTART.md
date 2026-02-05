# Glooko Data Query - Quick Reference

## What Is It?

Ask natural language questions about your diabetes data directly in the chat. The system analyzes your Glooko exports and answers with specific metrics.

## Before You Start

1. ✅ Upload your Glooko export via "Data Analysis" tab
2. ✅ Wait for analysis to complete
3. ✅ Return to Chat tab
4. ✅ Ask your question

## Question Examples

### "What was my average glucose last week?"
```
Expected answer: "145 mg/dL based on 142 readings..."
```

### "What's my time in range?"
```
Expected answer: "68% - below the 70% ADA target..."
```

### "When do I experience lows?"
```
Expected answer: Pattern analysis with times and frequency...
```

### "How's my glucose trend?"
```
Expected answer: Trend direction with improvement suggestions...
```

### "Do I have dawn phenomenon?"
```
Expected answer: Pattern details with confidence and recommendations...
```

## How It Works

| Step | What Happens |
|------|-------------|
| 1. You ask | "What was my average glucose last week?" |
| 2. System recognizes | Query is about your personal data → routes to GlookoQueryAgent |
| 3. AI parses question | Extracts: metric=glucose, period=last_week, aggregation=average |
| 4. Load your data | Finds latest analysis from your uploads |
| 5. Calculate answer | Runs query on your metrics |
| 6. Format response | Adds context, disclaimers, date range |
| 7. Safety check | Verifies response is appropriate |
| 8. Display | Shows with 📊 badge and source attribution |

## Question Types

### 📊 Temporal (Time-based)
- "last week", "January 15-20", "past month"
- Handles relative and absolute dates
- Example: "Average glucose last Thursday?"

### 📊 Metric (Calculations)
- "average", "time in range", "how many", "total"
- Returns values with units and context
- Example: "What's my average glucose?"

### 📊 Pattern (Recurring phenomena)
- "when", "pattern", "trend", "usually"
- Returns pattern confidence and recommendations
- Example: "When do I spike after meals?"

### 📊 Trend (Changes over time)
- "improving", "worse", "trending", "compared to"
- Returns directional analysis
- Example: "Is my TIR improving?"

## Response Format

Each answer includes:

```
📊 Your Glooko Data          ← Classification badge
✓ INFO                        ← Safety level

[Your answer with metrics]    ← Main response

Date range: Jan 21-27, 2026   ← Context
Reading count: 142             ← Sample size

Sources: Your Glooko Data     ← Attribution

Note: Discuss with your       ← Important reminder
healthcare team.
```

## Tips & Tricks

### ✅ DO
- ✅ Ask clear questions: "What was my average glucose last week?"
- ✅ Specify time periods: "In the past 2 weeks"
- ✅ Ask about metrics: "How many readings were low?"
- ✅ Discuss results with your healthcare team
- ✅ Upload new data for fresh analysis

### ❌ DON'T
- ❌ Expect specific insulin dose recommendations
- ❌ Rely solely on analysis for medical decisions
- ❌ Ask about future predictions
- ❌ Change management without talking to your team
- ❌ Assume patterns are causation

## Common Questions Answered

### "How do I upload data?"
Go to "Data Analysis" tab → Drag & drop or click to upload → Wait for analysis

### "Why is my question not being answered?"
- Make sure Glooko data is uploaded
- Try rephrasing: "What was my average glucose?" instead of "Average?"
- Check if metric is available in analysis

### "The answer seems wrong"
- Verify Glooko file was processed correctly
- Check analysis date is recent
- Try asking more specific question

### "Can it recommend insulin doses?"
No - always discuss trends with your healthcare team. System prevents prescriptive advice for safety.

### "How often should I upload data?"
As often as you want fresh analysis. Typically weekly or after pattern changes.

## What Data It Can Analyze

| Metric | Available | Example |
|--------|-----------|---------|
| Glucose readings | ✅ Yes | Average, distribution, trends |
| Time in range | ✅ Yes | TIR %, TAR %, TBR % |
| Patterns | ✅ Yes | Dawn phenomenon, post-meal spikes |
| Trends | ✅ Yes | Improving, declining, stable |
| Events | ✅ Yes | Low frequency, counts |
| Insulin correlation | ⚠️ Limited | Basic analysis only |
| Activity correlation | ⚠️ Limited | If logged in Glooko |

## Important Safety Notes

🚨 **This is educational analysis only**
- NOT a medical device
- NOT a replacement for healthcare team
- Should NOT be used for critical decisions
- ALWAYS discuss with your doctor

📋 **Data Privacy**
- All analysis happens on YOUR computer
- No data sent to external servers
- Safe and private

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Enter | Send question |
| Escape | Close any open modals |
| Tab | Navigate between elements |

## Suggested Questions to Try

**Beginner:**
- "What was my average glucose last week?"
- "What's my time in range?"
- "How many readings did I have?"

**Intermediate:**
- "When do I typically experience lows?"
- "Do I have a dawn phenomenon pattern?"
- "How does my glucose trend after meals?"

**Advanced:**
- "Compare my time in range this week vs last week"
- "What's my insulin sensitivity trend?"
- "When is my glucose most variable?"

## Troubleshooting

### No response or error
```
Error: "No Glooko data found"
→ Solution: Upload your Glooko export file first
```

### Question misunderstood
```
Response: "I'm not sure which metric..."
→ Solution: Try more specific question (e.g., "average" not "glucose")
```

### Data seems outdated
```
Warning: "Your data is 7 days old"
→ Solution: Upload a fresh Glooko export
```

### Missing specific metric
```
Response: "That metric isn't available yet"
→ Solution: Metric may not be in analysis, try different question
```

## Learning More

📖 **User Guide:** [WEB_INTERFACE.md](WEB_INTERFACE.md#glooko-data-queries)
📋 **Technical Guide:** [GLOOKO_INTEGRATION.md](GLOOKO_INTEGRATION.md#7-glooko-data-queries)
🏗️ **Architecture:** [GLOOKO_QUERY_ARCHITECTURE.md](GLOOKO_QUERY_ARCHITECTURE.md)
✅ **What's New:** [PHASE2_COMPLETE.md](PHASE2_COMPLETE.md)

---

**Remember:** This tool is your helper, not your doctor. 
Always discuss diabetes management changes with your healthcare team. 🏥
