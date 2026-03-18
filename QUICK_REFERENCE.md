# Quick Reference: Deterministic Layer & RAG Integration

**For Non-Technical Colleagues — One-Page Summary**

---

## **What Is This System? (30-Second Version)**

A calculator that compares two wealth transfer strategies (GRAT and CRAT) and projects tax benefits. It uses:
- Your client's situation (age, money, taxes)
- Current IRS interest rates (from official sources)
- Fixed mathematical formulas (never change)

Result: Auditable numbers you can explain to clients and tax professionals.

---

## **Three Key Questions**

### **Q1: How Do Hard Rules Work With Flexible Information?**

**Hard Rules** (Never change):
- GRAT runs for exactly 10 years
- CRAT runs for exactly 20 years
- Money grows at 5% per year (our assumption)

**Flexible Information** (Changes with time):
- IRS interest rates (1.96% in 2015, 4.2% in 2026)
- Client profiles (age, money amount, tax situation)
- Configuration settings (growth rate, payout rates)

**Priority:** Client data + current IRS rates **always override** old defaults.

**Impact:** Using the correct 2015 rate (1.96% instead of guessed 4.2%) changed outcomes by $2-3M per strategy.

---

### **Q2: What Assumptions Are Baked In?**

**"Safe" Assumptions** (Mostly reasonable):
- Client survives the full trust term ⚠️ (Critical for success)
- Investments grow at 5% every year ⚠️ (Optimistic in downturns)
- Your profile information is accurate ⚠️ (Garbage in, garbage out)
- Tax rates stay the same ⚠️ (Can change with legislation)

**⚠️ = Something to discuss with your tax team**

---

### **Q3: Where Could It Break?**

| Problem | Impact | Solution |
|---------|--------|----------|
| Client dies before 10 years | GRAT fails, no tax benefit | Life insurance, contingency planning |
| Market crashes -30% | Projections way off | Run multiple scenarios (3%, 5%, 7% growth) |
| Data entered wrong (wrong age, wrong year) | All numbers wrong but look right | Verify profile before running |
| Tax laws change | Exemptions/rates outdated | Annual review of settings |
| IRS rate not in table | System breaks (error message) | Manually provide rate, or wait for update |

---

## **Quick Interpretation Guide**

### **For a $16M Estate, Age 62 (2015 timing):**

| Strategy | Annual Payment | To Children/Charity | Tax Savings |
|----------|----------------|-------------------|------------|
| **GRAT** | $1.78M to you | $3.71M to children | $1.48M saved |
| **CRAT** | $0.80M to you | $16M to charity | $3.05M saved* |

*CRAT saves more because $16M goes to charity instead of staying in taxable estate

**In Plain English:**
- GRAT: Keep the money growing, protect kids' inheritance
- CRAT: Give money to charity, get big tax deduction now

---

## **What You Can Trust (& What You Can't)**

### ✅ **Reliable:**
- The comparison (GRAT vs. CRAT) is apples-to-apples
- The math is correct for the inputs provided
- You can show these numbers to an accountant with confidence
- Every number traces back to a source

### ⚠️ **Use With Caution:**
- Numbers are based on **assumptions** (5% growth, survival, etc.)
- Real results depend on market performance
- Tax laws might change
- Actual investment returns will vary

### ❌ **Not Guaranteed:**
- This is NOT a promise of actual tax savings
- This is NOT if markets are down substantially
- This is NOT accounting for state taxes (only federal)
- This is NOT if you die before the trust term ends

---

## **Red Flags (When to Get a Second Opinion)**

🚨 **STOP and verify with tax/legal team if:**
1. Client is in poor health (mortality risk changes everything)
2. Market is extremely volatile (5% assumption is too simplistic)
3. Client wants a different trust term (system only does 10 or 20 years)
4. Tax situation is complex (multiple states, trusts, etc.)
5. Numbers seem too good to be true (often just IRS rate optimization)

---

## **The Technical-ish Explanation (If Needed)**

**Why does the interest rate matter so much?**

Imagine lending $100 to someone. The lower the interest rate:
- Less money they need to pay back each year
- More money stays in the trust growing
- More money available for beneficiaries or charity at the end

2015: Low rates (1.96%) = Larger benefit
2026: High rates (4.2%) = Smaller benefit

Same strategy, different rates = **very different outcomes** ($3.7M vs. $1.0M for GRAT remainder).

---

## **When to Run This Calculator**

### ✅ **Good times:**
- Client wants to explore options (GRAT vs. CRAT)
- Need numbers for tax planning
- Creating a compliance audit trail
- Presenting to accountant/lawyer

### ❌ **Bad times:**
- Trying to predict exact future results
- Market is in crisis (revisit your projections)
- Client is elderly or in poor health (need mortality analysis)
- Tax laws recently changed (verify rates first)

---

## **What to Tell Clients**

**"Here's what the numbers show..."**
- This shows what each strategy **could** do based on reasonable assumptions
- Your actual results depend on market performance and life circumstances
- These numbers are good for comparing strategies, not predicting the future
- Your tax team should review these before making a decision

**"What's important to know..."**
- If you die before the trust term ends, the strategy doesn't work as planned
- If the stock market crashes, the numbers will be worse
- If tax laws change, we'll need to recalculate
- These are starting points for a conversation, not the final answer

---

## **Questions to Ask Your Technical Team**

1. **"When was the client profile last verified?"** (Should be < 1 year)
2. **"Are we using the right Section 7520 rate for the valuation date?"** (Tech team can confirm)
3. **"Have we run multiple growth scenarios?"** (Only if you want risk assessment)
4. **"What would this look like if the client died in year 5?"** (Requires additional model)
5. **"Are these numbers consistent with our tax team's analysis?"** (Always cross-check)

---

## **How It All Fits Together (The Pipeline)**

```
Step 1: You provide client info
        ↓
Step 2: System looks up IRS interest rate for that year
        ↓
Step 3: System runs two trust scenarios (GRAT + CRAT)
        ↓
Step 4: System outputs numbers in a report
        ↓
Step 5: AI writes a narrative explanation (using Step 4 numbers)
        ↓
Step 6: Report reviewed by human (you/your team)
        ↓
Step 7: Report delivered to client
```

**Key:** Every step can be traced. If something's wrong, tech team can show exactly where.

---

## **Bottom Line**

✅ **This system is good for: Reliable, auditable, comparable trust projections**

⚠️ **This system is bad for: Exact predictions, complex strategies, mortality analysis**

🎯 **Use it for: Planning conversations, option comparison, compliance trails**

❌ **Don't use it for: Medical/mortality analysis, market predictions, complex tax situations**

---

**Questions? Ask your tax advisor or technical lead to walk you through the DEEP_DIVE_ANALYSIS.md for details.**
