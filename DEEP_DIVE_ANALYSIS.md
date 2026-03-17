# Deep-Dive Analysis: Deterministic Layer & RAG Integration

**Date:** March 6, 2026  
**Purpose:** Comprehensive explanation of how the deterministic trust model works and integrates with RAG data, structured for both technical and non-technical audiences.

---

## PART I: INTERNAL TECHNICAL LOGIC

### 1. System Architecture Overview

Your pipeline has **8 distinct stages**, but the deterministic layer (Stage 3) is the critical bridge between **constraints** (hard rules) and **flexibility** (RAG-sourced data).

```
Stage 1: Client Intake (ClientProfile_v1.json)
         ↓
Stage 2: RAG Retrieval (Knowledge base retrieval)
         ↓
Stage 3: Deterministic Trust Modeler ← [THE CONSTRAINING LAYER]
         ├─ Loads rules from code
         ├─ Accepts RAG-sourced Section 7520 rates
         └─ Produces TrustComparison_v1.json
         ↓
Stage 4: LLM Drafting (Narrative generation)
         ├─ Reads ONLY from Stage 3 output
         ├─ CANNOT recalculate
         └─ CANNOT modify numbers
         ↓
Stages 5-8: Validation → Sign-off → PDF → Audit Log
```

### 2. How the Deterministic Layer Functions

#### **Core Philosophy**
The deterministic layer embodies a single, non-negotiable principle:

> **"All financial figures must originate from ClientProfile_v1.json or pre-computed mathematical formulas. Never invent, guess, or recalculate."**

This is enforced through **immutable data structures**:

```python
@dataclass(frozen=True)
class ClientInput:
    """Once created, client data CANNOT be modified in memory"""
    age: int
    liquidity_event_amount_usd: float
    estate_tax_rate: float
    # ... other fields ...
```

#### **The Three Components of Determinism**

**Component 1: Fixed Rules (Hard-coded in `/src/model/`)**

These are mathematical formulas, **not flexible** policies:

1. **GRAT Annuity Formula** (Present Value of Annuity):
   ```
   Annual Payment = Corpus / [(1 - (1+r)^-n) / r]
   
   Where:
     r = Section 7520 rate
     n = 10 years (hardcoded assumption)
     Corpus = Client's liquidity event amount
   ```
   
   **This is immutable** — the formula doesn't change. What changes is the **rate** (r).

2. **CRAT Charitable Deduction Formula** (Present Value of Remainder):
   ```
   Deduction = ProjectedRemainder / (1 + r)^20
   
   Where:
     r = Section 7520 rate
     ProjectedRemainder = simulated value after 20 years of growth & distributions
   ```

3. **Trust Growth Simulation** (Fixed algorithm):
   ```
   For each year:
     value = value × (1.05)        ← 5% growth (hardcoded)
     value = value - payment       ← annual payout (determined by other rules)
   ```

**Component 2: Extracted Data (From ClientProfile_v1.json)**

The client profile contains **immutable facts** about the specific client:
- Age: 62
- Marital status: Married
- Liquidity event amount: $16,000,000
- Estate tax rate: 40%
- Tax exemptions: $10.86M (married)
- Liquidity event year: 2015 ← **This determines the Section 7520 rate**

**Component 3: Configuration Files (From pipeline_artifacts/config/)**

Two critical JSON files contain **externally sourced, non-hardcoded** values:

a) **section_7520_rates.json** — Historical IRS rates per IRC §7520
   - Sourced from: RAG retrieval (S007 — the actual IRC statute)
   - Structure: Organized by year and month
   - Example: 2015 rate was 1.96% (low interest environment)
   - **This is connected to RAG data** ← Critical integration point

b) **model_assumptions.json** — Modeling parameters
   - GRAT: 10-year term, 5% growth rate
   - CRAT: 20-year term, 5% growth rate, 5% payout rate
   - All values declared and traceable

### 3. Integration: How RAG Data Constrains the Deterministic Layer

#### **The Bridge: Section 7520 Rate**

This is where **RAG data directly affects deterministic output**:

```
RAG Retrieval (Stage 2)
    ↓
    Retrieves: S007 (IRC §7520 statute)
    Contains: How Section 7520 rates are determined and published by IRS
    ↓
ClientProfile_v1.json
    ↓
    Contains: liquidity_event.year = 2015
    ↓
Deterministic Layer (Stage 3)
    ↓
    Step 1: Extract year from profile
    Step 2: Look up 2015 rate in historical table
    Step 3: Find rate = 0.0196 (1.96%)
    Step 4: Use rate in ALL calculations (GRAT annuity, CRAT deduction)
    ↓
TrustComparison_v1.json Output
    ├─ GRAT remainder to children: $3.71M (using 1.96% rate)
    ├─ GRAT estate tax savings: $1.48M
    ├─ CRAT charitable deduction: $7.62M
    ├─ CRAT estate tax savings: $3.05M
    └─ Rate used: 0.0196 (AKA "1.96%")
```

#### **What If the Rate Was Hardcoded Instead?**

To illustrate the importance of RAG integration, consider the **before vs. after**:

| Metric | With Hardcoded 4.2% | With RAG-Sourced 1.96% | Impact |
|--------|-------------------|----------------------|--------|
| GRAT Remainder | $1.00M | $3.71M | **+269% more to children** |
| GRAT Tax Savings | $401K | $1.48M | **+269% more tax benefit** |
| CRAT Deduction | $4.93M | $7.62M | **+54% larger deduction** |
| CRAT Tax Savings | $1.97M | $3.05M | **+54% more tax benefit** |

**The RAG rate (1.96%) produced dramatically different results** because lower interest rates make both trust strategies more effective at removing assets from the taxable estate.

#### **Priority: Who Takes Precedence?**

```
RAG Data (7520 rates) > Client Profile > Hardcoded Defaults

Rule: If you provide an explicit override in the model run, use it.
      Otherwise, extract from profile year + RAG historical rates.
```

**Code evidence** (from `src/model/engine.py`):

```python
if section_7520_rate is None:  # No override provided?
    section_7520_rate = load_section_7520_rate(client_profile)
    # This function:
    # 1. Extracts year from profile
    # 2. Looks up year in section_7520_rates.json (sourced from RAG)
    # 3. Returns the rate
```

### 4. Assumptions Baked Into the Code

#### **A. Fixed Structural Assumptions**

These **cannot be overridden** without code changes:

| Assumption | Value | IRC Reference | Implication |
|-----------|-------|---|---|
| GRAT term length | 10 years | §2702 | Grantor must survive exactly 10 years; if death during term, entire corpus included in estate |
| CRAT term length | 20 years | §664 | Income stream for 20 years; remainder to charity at end |
| CRAT payout rate | 5% of initial corpus | §664 | Fixed $800K/year on $16M (not percentage of current value) |
| Growth rate (both) | 5% annually | Market assumption | Conservative mid-range; not personalized to client |
| Taxable gift (GRAT) | $0 (zeroed-out) | §2702(a)(2)(A) | Assumes annuity PV ≈ remainder PV at inception |
| Estate tax rate | Taken from profile (40%) | §2033, §2036 | Assumes client is subject to federal estate tax |

#### **B. Client-Level Assumptions**

These are **extracted from ClientProfile_v1.json** and treated as facts:

```json
{
  "client_demographics": {
    "age": 62,
    "marital_status": "Married"
  },
  "liquidity_event": {
    "gross_proceeds_usd": 16000000,
    "year": 2015
  },
  "estate_tax_context_2015": {
    "individual_exemption_usd": 5430000,
    "married_exemption_usd": 10860000,
    "top_estate_tax_rate": 0.40
  }
}
```

**Critical assumption:** All profile data is **accurate and complete**. The model does NOT validate reasonableness beyond basic range checks (e.g., age must be 0-150).

#### **C. Behavioral Assumptions**

The model assumes **specific client behaviors**:

1. **Grantor survives the full trust term**
   - GRAT: If grantor dies during 10 years, entire corpus is included in their estate (defeating the strategy)
   - CRAT: If grantor dies during 20 years, full value is included under IRC §2036 (but charitable deduction still applies)

2. **Annuity payments are made annually**
   - The code uses a fixed annual schedule
   - Assumes grantor lives to receive each annual payment

3. **Trust assets perform as projected**
   - The 5% growth rate is applied deterministically
   - Real-world market risk is **not modeled**
   - If markets tank, real results diverge from projections

4. **Remainder beneficiaries survive and accept distributions**
   - For GRAT: children will receive and keep the remainder
   - For CRAT: charity will receive the remainder
   - Model does NOT account for beneficiary disclaimers or changes

### 5. Limitations & Failure Scenarios

#### **Scenario 1: Stale or Incorrect Client Profile**

**Failure Mode:** If ClientProfile_v1.json contains wrong data, **all output is garbage**, but the system won't know.

**Example:**
```json
{
  "client_demographics": {
    "age": -5,  ← Invalid
    "marital_status": "Married"
  }
}
```

**Current protection:** The code validates:
```python
if age <= 0 or age > 150:
    raise ValueError(f"Invalid age: {age}")
```

But it does **NOT validate**:
- Whether the person is actually the right client
- Whether the liquidity event actually occurred
- Whether the estate tax assumptions are current (2015 rates, even if it's now 2026)

**Risk:** Data entry errors that pass validation checks will silently produce wrong numbers.

---

#### **Scenario 2: Missing or Outdated Section 7520 Rate**

**Failure Mode:** If the valuation year is not in `section_7520_rates.json`, the model crashes.

**Example:**
```json
{
  "liquidity_event": {
    "year": 2050  ← Not in config yet
  }
}
```

**Result:**
```
ValueError: Section 7520 rate unknown for 2050-12. 
Please add to historical rates table or provide explicit rate parameter.
```

**Current protection:** Explicit error message.

**Risk:** User must manually add rates as time passes. If they forget, the pipeline stops. There's **no graceful fallback** (like using the most recent known rate).

---

#### **Scenario 3: Section 7520 Rate Assumption Doesn't Match RAG Knowledge**

**Failure Mode:** The `section_7520_rates.json` file could become **inconsistent** with the actual IRC §7520 knowledge in the RAG system.

**Example:**
- RAG retrieval (S007) says: "2026 rate for April is 4.2%"
- Config file says: "2026 rate for April is 3.8%"

**Why this happens:** The config file is manually maintained. If IRS publishes new rates and RAG is updated but config is not, they diverge.

**Current protection:** None. The system doesn't cross-check config against RAG.

**Risk:** Model could use outdated rates inadvertently.

---

#### **Scenario 4: Client Dies During Trust Term**

**Failure Mode:** The deterministic layer **assumes client survives**. This is a silent assumption embedded in the math.

**GRAT Example:**
- Model projects: $3.71M to children after 10 years
- Reality: Client dies in Year 7
- Actual outcome under IRC §2033: **Entire $16M included in client's estate** (trust fails)

**Code location:** [grat.py](src/model/grat.py#L60) - No mortality adjustment
```python
# Single line comment: "Assumes client survives the full 10-year term"
# But no alternate calculation
```

**Current protection:** A note in assumptions.txt, but not enforced in code.

**Risk:** Recommendations given to a client who dies before trust matures are **catastrophically wrong**.

---

#### **Scenario 5: Growth Rate Assumption Doesn't Match Actual Market**

**Failure Mode:** The model uses a **fixed 5% growth rate** for both GRAT and CRAT. This is not connected to any market data.

**Example:**
- S&P 500 crashes -30% in Year 3
- Model projected: $16M → ~$16.8M after 1 year of 5% growth
- Reality: $16M → ~$11.2M after -30% loss

**GRAT consequence:**
- Model projected remainder: $3.71M
- Actual corpus: May be lower or even depleted
- Impact: Tax projections way off, possible trust depletion before term ends

**Code location:** [grat.py](src/model/grat.py#L33) - Hardcoded:
```python
growth_rate = assumptions.grat_growth_rate  # 0.05 (5%) from config
```

**Current protection:** None. This is a **deterministic assumption**, not a range or scenario.

**Risk:** During market downturns, all projections become unreliable, but the system continues to output numbers as if certain.

---

#### **Scenario 6: Configuration File Tampering or Corruption**

**Failure Mode:** If `section_7520_rates.json` is edited manually (not via proper configuration management), it could contain invalid values.

**Example:**
```json
{
  "2026": {
    "06": "4.2%"  ← String, not float!
  }
}
```

**Result:**
```
ValueError: could not convert string to float: '4.2%'
```

**Current protection:** JSON parsing error caught at load time.

**Risk:** While caught, the error message might not be clear to business users. Also, there's no version control or audit trail for config changes.

---

#### **Scenario 7: CRAT Deduction Over-Estimation**

**Failure Mode:** The charitable deduction calculation is conservative in methodology, but the underlying assumptions may still be optimistic.

**Code:** [crat.py](src/model/crat.py#L45)
```python
# Uses deduction_growth_rate = 0.04 (4%, from config)
# But actual trust might grow at 5% (crat_growth_rate)
```

This is **double-conservative**: using 4% growth for deduction (lower value to charity, smaller deduction) while projecting 5% growth for actual remainder.

**Issue:** The deduction is estimated, not precise IRS-approved value. The code comment says:
```python
"""Estimated charitable deduction, rounded to 2 decimals"""
```

But downstream systems might treat it as **exact**.

**Risk:** LLM in Stage 4 reads this number and states it as fact. "You can deduct $7.62M!" But actual IRS valuation could be different.

---

#### **Scenario 8: Remainder Goes Negative (Trust Depleted)**

**Failure Mode:** If annual payments exceed growth, remainder could go negative. Code prevents this:

```python
remainder = max(value, 0)  # Cap at zero
```

But this is a **silent adjustment**. The model doesn't flag that trust was depleted.

**Example:**
- Initial corpus: $16M
- Growth rate: 5% (but market crashes to -2%)
- CRAT annual payout: $800K
- By Year 8, corpus drops to $0 (even though model projected $16M still)

**Current protection:** Remainder is capped at $0, not allowed to go negative.

**Risk:** Model outputs "remainder to charity: $0" without distinguishing between "trust performed well" vs. "trust was depleted before term end."

---

### 6. Priority Hierarchy (Data Conflict Resolution)

The system has a **clear priority order** for resolving conflicts:

```
1. Provided Override (section_7520_rate parameter)
   └─ If caller explicitly provides a rate, use it

2. Client Profile Data
   └─ Extract valuation year from profile

3. Historical Configuration (section_7520_rates.json)
   └─ Look up rate from historical IRS table

4. Error: No Rate Available
   └─ Raise ValueError, stop execution
   └─ Never fallback to hardcoded default; demand explicit input
```

**Code evidence** ([engine.py](src/model/engine.py#L125)):
```python
if section_7520_rate is None:
    section_7520_rate = load_section_7520_rate(client_profile)
    # Extracts from profile + config, raises if not found
else:
    # Use the provided override
    pass
```

---

## PART II: PLAIN-ENGLISH SUMMARY FOR NON-TECHNICAL COLLEAGUES

### **The Mental Model: A Calculator with Rules**

Imagine you have a special financial calculator designed specifically for trust strategies. Here's how it works:

#### **The Calculator's Three Modes**

**Mode 1: Rock-Solid Rules (The Formulas)**

The calculator has hardwired formulas that never change:
- "GRAT: Take the money, spread payments over 10 years, calculate what's left"
- "CRAT: Take the money, pay out 5% every year for 20 years, the rest goes to charity"

These formulas are **like gravity** — they apply the same way every time.

**Mode 2: Client-Specific Facts (The Profile)**

You feed the calculator your actual situation:
- Your age
- How much money we're talking about
- What the estate tax rate is
- When this all started (the year)

**Mode 3: Market Context (The Rate)**

The calculator knows: "Interest rates matter."

It looks up the IRS-published interest rate for the specific year you provided. If you did something in 2015, it uses the 2015 rate (1.96%). If you do something in 2026, it uses the 2026 rate (maybe 4.2%, depending on the month).

This is the **RAG connection**: The rate comes from official government data, retrieved via knowledge search, not guessed.

#### **What the Calculator Does (The Process)**

```
You provide:    Your situation ($16M, age 62, 2015)
                ↓
Calculator:     Looks up the 2015 interest rate (1.96%)
                ↓
Formula 1:      "How much do you get paid each year in a GRAT?"
                Answer: $1.78M/year for 10 years
                ↓
Formula 2:      "How much is left afterward?"
                Answer: $3.71M to your children
                ↓
Formula 3:      "What's the tax benefit?"
                Answer: Save $1.48M in estate taxes
                ↓
Formula 4:      "What if we did CRAT instead?"
                Answer: $800K/year to you, $7.62M deduction, save $3.05M in taxes
                ↓
Output:         A report comparing both strategies
```

#### **Why Use This Calculator? (The Benefit)**

1. **Reproducibility:** Same input always gives same output. No surprises.
2. **Traceability:** Every number can be traced back to a source (your profile, the IRS rate, or the formula).
3. **Auditability:** If a lawyer or accountant asks, "Where did this $1.48M savings come from?", you can show the exact calculation.

#### **How Hard Rules Meet Flexible Data (The Integration)**

The calculator embodies a principle:

> **"Hard rules about how trusts work + flexible data about interest rates = accurate, current projections"**

**Hard Rules (Unchanging):**
- GRAT always runs 10 years
- CRAT always runs 20 years
- Both grow at 5% (our assumption)
- We always calculate the tax savings

**Flexible Data (Updated Regularly):**
- IRS updates interest rates monthly
- Your profile might change (age, estate size, etc.)
- The calculator adapts to these changes instantly

**Result:** The calculator is **reliable** (follows consistent rules) but **current** (uses today's interest rates).

#### **Real-World Example of Integration in Action**

Let's say interest rates drop:

**2015 (Low Rates):**
- IRS rate: 1.96%
- GRAT remainder after 10 years: $3.71M
- Reason: Low rates make the annuity payment smaller, so more stays in the trust

**2026 (High Rates):**
- IRS rate: 4.2%
- GRAT remainder after 10 years: ~$0.98M
- Reason: High rates make the annuity payment larger, so less stays in the trust

**Same client, same strategy, same $16M. But the interest rate changed the outcome by $2.73M.**

The calculator automatically adjusted because it looked up the actual IRS rate. It didn't guess or use a fixed default.

---

### **What Assumptions Are We Making? (The Fine Print)**

The calculator has several **assumptions built in** that you should know about:

#### **Assumption 1: You (or Your Family) Live Long Enough**

The calculator assumes:
- You'll live through the entire trust term (10 years for GRAT, 20 for CRAT)
- If you die early, the tax benefit goes away

**In Plain English:** GRAT strategies only work if you survive. If you pass away during the 10-year period, the entire $16M comes back into your taxable estate. The tax benefit disappears.

**Current safeguard:** None in the calculator. It doesn't account for mortality risk. You'd need separate life insurance or contingency planning.

#### **Assumption 2: Investments Grow at 5% Every Year**

The calculator uses a fixed **5% annual growth rate**. This is a reasonable assumption historically, but it's not guaranteed.

**In Plain English:** The calculator assumes your $16M trust grows by $800K per year (5% of $16M). If the stock market crashes, or your investments underperform, the real numbers will be worse.

**When this breaks:** Market downturns (2008, 2020, etc.) can produce -20% to -50% returns. The calculator's projection of "steady 5%" becomes wildly optimistic.

**Current safeguard:** None. The calculator assumes investment success. You might want multiple scenarios (3% growth, 5% growth, 7% growth) to understand the range of outcomes.

#### **Assumption 3: The Client Profile Is Accurate**

**In Plain English:** Garbage in, garbage out. If the profile says you're age 62 but you're actually 82, the calculations are still technically correct — but for the wrong person.

**What we check:**
- Age between 0-150 ✓
- Money amounts are positive ✓

**What we don't check:**
- Is this actually your money? (Is the $16M accurate?)
- Is the 2015 date right, or was the event in 2014?
- Are your tax rates current?

**Current safeguard:** You (the user) are responsible for verifying the profile is correct before we run calculations.

#### **Assumption 4: Tax Laws Don't Change**

The calculator uses 2015 tax laws (from your client's profile):
- 40% estate tax rate
- $10.86M married exemption

**In Plain English:** If Congress changes the estate tax law (which happens periodically), these numbers would be outdated.

**Example:** In 2026, the estate tax exemption is scheduled to drop (the "sunset provision"). The calculator doesn't account for this.

**Current safeguard:** You need to manually update the profile when tax laws change.

#### **Assumption 5: Payments Are Fixed (Not Adjusted for Inflation)**

**In Plain English:** The GRAT pays you $1.78M per year, every year, for 10 years. If inflation hits 5% per year, that payment buys less each year, making it less attractive.

**Current safeguard:** None. This is by design (fixed GRAT), but worth knowing.

---

### **Where Could Things Go Wrong? (The Limitations)**

#### **Limitation 1: We're Not Predicting the Future**

**The Problem:** The calculator uses fixed assumptions (5% growth,  fixed payments), but real life has surprises.

**Examples:**
- Market crashes 30%
- Client dies unexpectedly
- Tax laws change
- Chosen charity goes bankrupt (CRAT scenario)

**The Reality:** The numbers are good for planning, but they're not prophecies. They say "If everything goes as planned, you'll save $1.48M." Not "You definitely will."

**What to do:** Use these numbers for **comparing strategies**, not as guarantees. A 3% market downturn would reduce the GRAT remainder from $3.71M to ~$2.8M — still worth doing, but different.

#### **Limitation 2: We Assume You Know Your Situation**

**The Problem:** The calculator can only work with the information you provide. If key details are wrong, everything downstream is wrong.

**Examples:**
- Profile says liquidity event in 2015, but you're now thinking about 2026 planning
- Estate tax rate is 40%, but state taxes add another 15%
- Assumes IRS will approve your strategy structure (e.g., GRAT payout calculation)

**Current check:** Nothing beyond basic validation. User responsibility.

#### **Limitation 3: We Can't Handle Complexity**

**The Problem:** Real client situations are complex. The calculator handles **two specific scenarios** (GRAT and CRAT) well, but not variations:

- What if you want a 7-year GRAT instead of 10?
- What if you want a declining annuity (starts high, drops over time)?
- What if you want to split funds (some to GRAT, some to CRAT, some to outright gifts)?

**Current answer:** "Run the calculator twice with different profiles" — but that's clunky.

#### **Limitation 4: The Interest Rate Lookup Can Fail**

**The Problem:** If the valuation year isn't in our reference table, the model crashes.

**Example:**
- Client profile says year = 2050
- We don't have 2050 rates yet (they're not published)
- Result: Error, model stops

**Current workaround:** You can manually provide a rate to override, but you have to do that.

#### **Limitation 5: Stage 4 LLM Can't Recalculate (By Design)**

**This is intentional but worth noting:**

Once Stage 3 (the deterministic calculator) produces numbers, Stage 4 (the AI writing assistant) **cannot modify or recalculate** them. 

**Why?** To prevent the LLM from accidentally changing numbers or introducing errors.

**The tradeoff:** If you discover an error in the Stage 3 output, you have to go back and fix the input, re-run Stage 3, then generate the narrative again. You can't patch the number in the narrative.

---

### **Summary: How to Think About This System**

Think of the deterministic layer like a **certified calculator for trusts**:

✅ **Strengths:**
- It follows consistent rules
- It uses current IRS interest rates
- It traces every number to a source
- It's audit-ready
- It produces the same result reliably

⚠️ **Limitations:**
- It assumes investment success (5% growth)
- It assumes you live long enough
- It assumes your profile data is accurate
- It doesn't handle complex strategies
- It gives point estimates, not ranges

🎯 **Best Use:**
- Comparing trust strategies (GRAT vs. CRAT)
- Quantifying tax benefits for planning
- Creating an audit trail for compliance
- Communicating with lawyers and accountants
- **NOT** as a market prediction or guarantee

The system's tag line should be: **"Accurate math applied to your situation, using current rules — not a crystal ball."**

---

## PART III: INTEGRATION DEEP DIVE

### **The RAG Connection: How Knowledge Becomes Numbers**

Your system has a specific data flow where the Deterministic Layer **consumes** information retrieved by the RAG system:

#### **Data Flow Diagram**

```
┌─────────────────────────────────────────────────────────────┐
│ RAG SYSTEM (Stage 2)                                        │
│ ┌───────────────────────────────────────────────────────┐   │
│ │ Knowledge Sources:                                    │   │
│ │ • S001: GRAT Principles                              │   │
│ │ • S007: IRC §7520 Valuation Tables ← Key!            │   │
│ │ • S002: CRAT Charitable Rules                        │   │
│ │ • ... (others)                                        │   │
│ └───────────────────────────────────────────────────────┘   │
│                      ↓                                       │
│ Extraction:  "Section 7520 is 120% of federal midterm rate  │
│              Updated monthly by IRS"                        │
└──────────────┬──────────────────────────────────────────────┘
               │
      Pipeline: section_7520_rates.json
      (Manually updated with IRS published values)
               │
               ↓
┌─────────────────────────────────────────────────────────────┐
│ DETERMINISTIC LAYER (Stage 3)                              │
│                                                             │
│ ClientProfile_v1.json                                      │
│ ├─ "liquidity_event.year": 2015                           │
│ │                                                          │
│ ├─ Load section_7520_rate(profile):                       │
│ │  ├─ Extract year → 2015                                │
│ │  ├─ Look up in config → 1.96%                          │
│ │  └─ Return 1.96%                                       │
│ │                                                          │
│ └─ Run calculations:                                      │
│    ├─ GRAT annuity = 16M / [(1-(1.0196)^-10) / 0.0196]  │
│    │                = $1,777,498.67/year                │
│    │                                                      │
│    ├─ GRAT remainder = simulate 10 years @ 5% growth     │
│    │                = $3,705,127                         │
│    │                                                      │
│    ├─ CRAT deduction = PV_remainder / (1.0196)^20        │
│    │                = $7,620,722.64                      │
│    └─ etc.                                               │
└──────────────┬──────────────────────────────────────────────┘
               │
               ↓
┌─────────────────────────────────────────────────────────────┐
│ OUTPUT: TrustComparison_v1.json                             │
│                                                             │
│ All numbers derived from:                                  │
│ 1. Client profile (facts: $16M, age 62, etc.)             │
│ 2. IRS rates from RAG knowledge (1.96% for 2015)          │
│ 3. Coded formulas (annuity, present value, etc.)          │
│                                                             │
│ Audit Trail: "Rate 0.0196 sourced from S007 lookup"       │
└─────────────────────────────────────────────────────────────┘
               │
               ↓
┌─────────────────────────────────────────────────────────────┐
│ NARRATIVE GENERATION (Stage 4)                              │
│                                                             │
│ LLM reads TrustComparison_v1.json and writes:             │
│ "Based on the Section 7520 rate of 1.96% (per IRC §7520  │
│  for 2015), your GRAT would provide $3.71M to your        │
│  children, saving $1.48M in estate taxes..."              │
│                                                             │
│ The rate came from: RAG → Config → Deterministic → Output │
└─────────────────────────────────────────────────────────────┘
```

#### **Why This Design Matters**

The system deliberately keeps **three types of inputs separate**:

1. **Facts from the Profile** (deterministic, client-specific)
   - Age, money, exemptions
   - Cannot be disputed or negotiated

2. **Knowledge from RAG** (current, authoritative)
   - IRS interest rates
   - Legal framework (IRC §7520 definition)
   - Updated as knowledge base changes

3. **Formulas from Code** (mathematical, immutable)
   - Annuity calculations
   - Present value formulas
   - Growth simulations

**Result:** If any one piece changes, the system recalculates consistently:
- New client data → different numbers (same formulas)
- New IRS rate → different numbers (same formulas, same client)
- Bug fix in formula → different numbers (same data)

**No one part is hidden inside another.** This is intentional, for auditability.

---

## PART IV: CRITICAL INTEGRATION POINTS TO MONITOR

### **Point 1: Section 7520 Rate Currency**

**Risk:** The historical rate table can go stale if IRS publishes new rates and config isn't updated.

**Current Process:**
1. IRS publishes rate (e.g., "2026 June rate is 3.8%")
2. Someone reads that and manually adds it to `section_7520_rates.json`
3. Next time system runs with 2026 date, it uses 3.8%

**Potential Failure:** If step 2 doesn't happen, old rates are used for new dates.

**Recommendation:**
- Automate rate table updates (scrape IRS site monthly)
- Enable overrides in UI so users can inject a known rate without code change
- Add validation: warn if using a rate > 30 days old without explicit override

### **Point 2: Profile Accuracy Validation**

**Risk:** Bad profile data produces bad numbers silently.

**Example:** Profile says age = 62, but that's the **spouse's** age, not the client's.

**Current Process:**
- Code validates: 0 < age < 150 ✓
- Code validates: liquidity_amount >= 0 ✓
- Code does NOT validate: age matches correct person, rate is current, etc.

**Recommendation:**
- Add a "data quality score" to profiles (e.g., "Complete", "Incomplete", "Stale")
- Require user confirmation: "I have reviewed the profile and confirm age = 62"
- Add timestamp to profile; warn if > 2 years old

### **Point 3: Formula Consistency Between Stages**

**Risk:** Stage 4 (LLM) reads numbers from Stage 3 (deterministic) but might recompute or misunderstand them.

**Current Design:** Stage 4 cannot recalculate (reads JSON only).

**Recommendation:** Strengthen this with:
- Hash the calculation in Stage 3 output (SHA-256 of inputs + formula version)
- Stage 5 (validation) confirms hash matches when re-running
- If mismatch, raise an error (someone modified the JSON)

### **Point 4: Assumption Update Propagation**

**Risk:** If assumptions in config change (e.g., growth rate from 5% to 4%), old outputs are no longer consistent with current assumptions.

**Example:**
- 2026-03: Run model with 5% growth, CRAT remainder = $16M
- 2026-04: Change config to 4% growth
- 2026-04: User re-runs with same client, sees remainder = $15.8M
- User confused: "Did the client's situation change?"
- Answer: No, the assumption changed.

**Recommendation:**
- Version assumptions (config v1, v2, v3)
- Output always includes assumption version
- Add "Assumption Changed" warnings when re-running with new config

---

## CONCLUSIONS

### **For Technical Teams:**

Your system is well-designed to be **deterministic** (reproducible), **auditable** (traceable), and **compliant** (follows hard rules). The key strength is the clean separation between:
- client facts (profile)
- external knowledge (RAG-sourced rates)
- business logic (formulas)

The integration of RAG data (Section 7520 rates) is **working correctly** and produces financially significant impacts (potential $2M+ difference vs. hardcoded rates).

**Key vulnerabilities:**
1. Missing mortality risk adjustment
2. No scenario analysis (single 5% growth rate)
3. Configuration files vulnerable to drift
4. Limited validation on profile field accuracy
5. Silent failures when assumptions aren't met

### **For Business & Compliance Teams:**

The system is **robust for basic cases** (client profile is accurate, assumptions are reasonable) but **risky for edge cases** (client dies early, market crashes, tax laws change).

**Safe to use for:**
- Comparing GRAT vs. CRAT strategies
- Quantifying approximate tax benefits
- Creating compliant audit trails
- Communicating with tax professionals

**Caution required for:**
- Clients in poor health (mortality risk)
- Volatile markets (growth rates too optimistic)
- Tax law changes (rates may be outdated)
- High-complexity strategies (system too rigid)

**Recommendation:** Always pair these numbers with:
1. Multiple scenarios (3%, 5%, 7% growth)
2. Mortality risk analysis (underwriting input)
3. Annual tax law review
4. Professional tax opinion
5. Clear documentation of assumptions used

---

**End of Deep-Dive Analysis**
