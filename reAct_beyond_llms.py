from dataclasses import dataclass, field
from typing import Optional, List, Tuple
import uuid
import datetime

# =======================
# Domain Model & Memory
# =======================

@dataclass
class Invoice:
    invoice_id: str
    vendor_id: str
    amount: int  # cents
    currency: str
    due_date: datetime.date
    memo: str

@dataclass
class Account:
    account_id: str
    balance_cents: int
    daily_limit_cents: int
    spent_today_cents: int = 0

@dataclass
class PaymentPlan:
    total_cents: int
    currency: str
    immediate_cents: int
    scheduled_cents: int = 0
    scheduled_date: Optional[datetime.date] = None

@dataclass
class Memory:
    invoice: Invoice
    account: Account
    vendor_kyc_ok: Optional[bool] = None
    vendor_aml_ok: Optional[bool] = None
    payment_plan: Optional[PaymentPlan] = None
    executed_amount_cents: int = 0
    scheduled: bool = False
    errors: List[str] = field(default_factory=list)
    audit_log: List[str] = field(default_factory=list)

    def log(self, msg: str):
        timestamp = datetime.datetime.now().isoformat(timespec="seconds")
        self.audit_log.append(f"{timestamp} | {msg}")
        print(msg)

# ================
# Tools (Actions)
# ================

def tool_validate_invoice(mem: Memory) -> Tuple[bool, str]:
    inv = mem.invoice
    if inv.amount <= 0:
        return False, "Invalid invoice amount."
    if inv.currency not in {"USD", "EUR", "GBP"}:
        return False, f"Unsupported currency {inv.currency}."
    if inv.due_date < datetime.date.today() - datetime.timedelta(days=30):
        return False, "Invoice is too old."
    return True, "Invoice validated."

def tool_run_kyc(vendor_id: str) -> Tuple[bool, str]:
    ok = not vendor_id.endswith("X")
    return ok, "KYC passed." if ok else "KYC failed."

def tool_run_aml_screening(vendor_id: str) -> Tuple[bool, str]:
    denylist = {"OFAC123", "AML999"}
    ok = vendor_id not in denylist
    return ok, "AML screening passed." if ok else "AML screening flagged vendor."

def tool_check_balance(acct: Account, amount_cents: int) -> Tuple[bool, str]:
    ok = acct.balance_cents >= amount_cents
    return ok, "Sufficient balance." if ok else "Insufficient balance."

def tool_check_daily_limit(acct: Account, amount_cents: int) -> Tuple[bool, str]:
    ok = (acct.spent_today_cents + amount_cents) <= acct.daily_limit_cents
    return ok, "Within daily limit." if ok else "Exceeds daily limit."

def tool_propose_plan(mem: Memory) -> Tuple[bool, str, PaymentPlan]:
    inv = mem.invoice
    acct = mem.account
    immediate = min(inv.amount, acct.balance_cents)
    remaining_limit = max(0, acct.daily_limit_cents - acct.spent_today_cents)
    immediate = min(immediate, remaining_limit)
    if immediate <= 0:
        plan = PaymentPlan(inv.amount, inv.currency, 0, inv.amount,
                           datetime.date.today() + datetime.timedelta(days=1))
        return True, "Proposed full scheduling for tomorrow.", plan
    remainder = inv.amount - immediate
    if remainder > 0:
        plan = PaymentPlan(inv.amount, inv.currency, immediate, remainder,
                           datetime.date.today() + datetime.timedelta(days=1))
        return True, "Proposed split: partial now, remainder tomorrow.", plan
    plan = PaymentPlan(inv.amount, inv.currency, inv.amount)
    return True, "Proposed full payment now.", plan

def tool_execute_payment(acct: Account, cents: int, currency: str) -> Tuple[bool, str, str]:
    if cents <= 0:
        return True, "Nothing to execute.", str(uuid.uuid4())
    if acct.balance_cents < cents:
        return False, "Execution failed: insufficient funds.", ""
    acct.balance_cents -= cents
    acct.spent_today_cents += cents
    txn_id = str(uuid.uuid4())
    return True, f"Executed {cents/100:.2f} {currency}.", txn_id

def tool_schedule_payment(date: datetime.date, cents: int, currency: str) -> Tuple[bool, str, str]:
    if cents <= 0:
        return True, "Nothing to schedule.", str(uuid.uuid4())
    sch_id = f"SCH-{uuid.uuid4()}"
    return True, f"Scheduled {cents/100:.2f} {currency} for {date}.", sch_id

# =======================
# Reasoner (Thought)
# =======================

class Reasoner:
    def next_action(self, mem: Memory) -> Optional[str]:
        if not any("Invoice validated." in line for line in mem.audit_log):
            return "validate_invoice"
        if mem.vendor_kyc_ok is None:
            return "run_kyc"
        if mem.vendor_aml_ok is None:
            return "run_aml"
        if mem.payment_plan is None:
            return "propose_plan"
        if mem.executed_amount_cents < mem.payment_plan.immediate_cents:
            return "execute_immediate"
        if not mem.scheduled and mem.payment_plan.scheduled_cents > 0:
            return "schedule_remainder"
        return None

# =======================
# ReAct Orchestrator
# =======================

def run_episode(mem: Memory):
    reasoner = Reasoner()
    step = 0
    while True:
        step += 1
        action = reasoner.next_action(mem)
        if action is None:
            mem.log(f"Thought {step}: Done.")
            break
        mem.log(f"Thought {step}: Deciding to '{action}'.")

        if action == "validate_invoice":
            ok, msg = tool_validate_invoice(mem)
            mem.log(f"Action {step}: validate_invoice()")
            mem.log(f"Observation {step}: {msg}")
            if not ok: break

        elif action == "run_kyc":
            ok, msg = tool_run_kyc(mem.invoice.vendor_id)
            mem.vendor_kyc_ok = ok
            mem.log(f"Action {step}: run_kyc({mem.invoice.vendor_id})")
            mem.log(f"Observation {step}: {msg}")
            if not ok: break

        elif action == "run_aml":
            ok, msg = tool_run_aml_screening(mem.invoice.vendor_id)
            mem.vendor_aml_ok = ok
            mem.log(f"Action {step}: run_aml({mem.invoice.vendor_id})")
            mem.log(f"Observation {step}: {msg}")
            if not ok: break

        elif action == "propose_plan":
            ok, msg, plan = tool_propose_plan(mem)
            mem.payment_plan = plan if ok else None
            mem.log(f"Action {step}: propose_plan()")
            mem.log(f"Observation {step}: {msg}")

        elif action == "execute_immediate":
            cents = mem.payment_plan.immediate_cents
            ok, msg, txn = tool_execute_payment(mem.account, cents, mem.payment_plan.currency)
            mem.log(f"Action {step}: execute_payment({cents/100:.2f} {mem.payment_plan.currency})")
            mem.log(f"Observation {step}: {msg} (txn={txn})")
            if ok: mem.executed_amount_cents = cents

        elif action == "schedule_remainder":
            cents = mem.payment_plan.scheduled_cents
            date = mem.payment_plan.scheduled_date
            ok, msg, sch = tool_schedule_payment(date, cents, mem.payment_plan.currency)
            mem.log(f"Action {step}: schedule_payment({cents/100:.2f} {mem.payment_plan.currency} on {date})")
            mem.log(f"Observation {step}: {msg} (id={sch})")
            if ok: mem.scheduled = True

# =======================
# Demo Run
# =======================

if __name__ == "__main__":
    invoice = Invoice("INV-1001", "ACME_CO", 250_00, "USD",
                      datetime.date.today() + datetime.timedelta(days=5),
                      "Monthly hosting fee")
    account = Account("OPERATING-USD", balance_cents=180_00, daily_limit_cents=500_00)
    mem = Memory(invoice, account)
    run_episode(mem)

    print("\n=== FINAL AUDIT LOG ===")
    for line in mem.audit_log:
        print(line)
