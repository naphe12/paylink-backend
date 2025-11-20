"""
Résolution globale des références croisées Pydantic (v2)
pour tous les schémas PayLink.
"""

from app.schemas import agentlocations, agents, countries, users

# Regroupe toutes les classes susceptibles de se référencer entre elles
MODELS = [
    users.UsersRead,
    countries.CountriesRead,
    agents.AgentsRead,
    agentlocations.AgentLocationsRead,
]

# Espace de noms global pour la résolution
TYPES_NAMESPACE = {
    "UsersRead": users.UsersRead,
    "CountriesRead": countries.CountriesRead,
    "AgentsRead": agents.AgentsRead,
    "AgentLocationsRead": agentlocations.AgentLocationsRead,
}

# Reconstruit chaque modèle avec les références connues
for model in MODELS:
    try:
        model.model_rebuild(_types_namespace=TYPES_NAMESPACE)
    except Exception:
        pass
from app.schemas.agents import AgentsRead
from app.schemas.amlevents import AmlEventsRead
from app.schemas.billpayments import BillPaymentsRead
from app.schemas.countries import CountriesRead
from app.schemas.currencies import CurrenciesRead
from app.schemas.disputes import DisputesRead
from app.schemas.feeschedules import FeeSchedulesRead
from app.schemas.fxconversions import FxConversionsRead
from app.schemas.fxrates import FxRatesRead
from app.schemas.invoices import InvoicesRead
from app.schemas.kycdocuments import KycDocumentsRead
from app.schemas.ledgeraccounts import LedgerAccountsRead
from app.schemas.ledgerentries import LedgerEntriesRead
from app.schemas.ledgerjournal import LedgerJournalRead
from app.schemas.limits import LimitsRead
from app.schemas.limitusage import LimitUsageRead
from app.schemas.loanrepayments import LoanRepaymentsRead
from app.schemas.loans import LoansRead
from app.schemas.merchants import MerchantsRead
from app.schemas.notifications import NotificationsRead
from app.schemas.paymentinstructions import PaymentInstructionsRead
from app.schemas.provideraccounts import ProviderAccountsRead
from app.schemas.providers import ProvidersRead
from app.schemas.reconfiles import ReconFilesRead
from app.schemas.reconlines import ReconLinesRead
from app.schemas.sanctionsscreening import SanctionsScreeningRead
from app.schemas.settlements import SettlementsRead
from app.schemas.tontinecontributions import TontineContributionsRead
from app.schemas.tontinemembers import TontineMembersRead
from app.schemas.tontinepayouts import TontinePayoutsRead
from app.schemas.tontines import TontinesRead
from app.schemas.transactions import TransactionsRead
from app.schemas.user_auth import UserAuthRead
from app.schemas.userdevices import UserDevicesRead
# 🔹 Importation de tous les schémas utilisés dans UsersRead
from app.schemas.users import UsersRead
from app.schemas.wallets import WalletsRead
from app.schemas.credit_line_history import CreditLineHistoryRead
from app.schemas.wallet_cash_requests import (
    WalletCashDecision,
    WalletCashDepositCreate,
    WalletCashRequestAdminRead,
    WalletCashRequestRead,
    WalletCashWithdrawCreate,
)

# app/schemas/__init__.py




# 🔧 Reconstruction après que TOUT soit chargé
UsersRead.model_rebuild()
UserAuthRead.model_rebuild()
CountriesRead.model_rebuild()
AgentsRead.model_rebuild()
KycDocumentsRead.model_rebuild()
LimitUsageRead.model_rebuild()
LoansRead.model_rebuild()
NotificationsRead.model_rebuild()
SanctionsScreeningRead.model_rebuild()
TontinesRead.model_rebuild()
UserDevicesRead.model_rebuild()
WalletsRead.model_rebuild()
MerchantsRead.model_rebuild()
TontineMembersRead.model_rebuild()
TransactionsRead.model_rebuild()
AmlEventsRead.model_rebuild()
DisputesRead.model_rebuild()
InvoicesRead.model_rebuild()
TontineContributionsRead.model_rebuild()
TontinePayoutsRead.model_rebuild()
FeeSchedulesRead.model_rebuild()
CurrenciesRead.model_rebuild()
FxConversionsRead.model_rebuild()
LimitsRead.model_rebuild()
InvoicesRead.model_rebuild()
BillPaymentsRead.model_rebuild()
FxRatesRead.model_rebuild()
LedgerAccountsRead.model_rebuild()
ProviderAccountsRead.model_rebuild()
LedgerEntriesRead.model_rebuild()
SettlementsRead.model_rebuild()
PaymentInstructionsRead.model_rebuild()
ReconLinesRead.model_rebuild()
ProvidersRead.model_rebuild()
ReconFilesRead.model_rebuild()
LoanRepaymentsRead.model_rebuild()
LedgerJournalRead.model_rebuild()
WalletCashRequestRead.model_rebuild()
WalletCashRequestAdminRead.model_rebuild()
CreditLineHistoryRead.model_rebuild()
# 🔄 Reconstruit tous les modèles après import
try:
    from app.schemas import AmlEventsRead
    AmlEventsRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import BillPaymentsRead
    BillPaymentsRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import CurrenciesRead
    CurrenciesRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import DisputesRead
    DisputesRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import FeeSchedulesRead
    FeeSchedulesRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import FxConversionsRead
    FxConversionsRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import FxRatesRead
    FxRatesRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import InvoicesRead
    InvoicesRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import LedgerAccountsRead
    LedgerAccountsRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import LedgerEntriesRead
    LedgerEntriesRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import LedgerJournalRead
    LedgerJournalRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import LimitUsageRead
    LimitUsageRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import LimitsRead
    LimitsRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import LoanRepaymentsRead
    LoanRepaymentsRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import LoansRead
    LoansRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import MerchantsRead
    MerchantsRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import PaymentInstructionsRead
    PaymentInstructionsRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import ProviderAccountsRead
    ProviderAccountsRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import ProvidersRead
    ProvidersRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import ReconFilesRead
    ReconFilesRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import ReconLinesRead
    ReconLinesRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import SettlementsRead
    SettlementsRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import TontineContributionsRead
    TontineContributionsRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import TontineMembersRead
    TontineMembersRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import TontinePayoutsRead
    TontinePayoutsRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import TontinesRead
    TontinesRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import TransactionsRead
    TransactionsRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import UsersRead, users
    UsersRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import WalletsRead
    WalletsRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import WebhookEventsRead
    WebhookEventsRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import WebhooksRead
    WebhooksRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import WalletCashRequestRead, WalletCashRequestAdminRead
    WalletCashRequestRead.model_rebuild()
    WalletCashRequestAdminRead.model_rebuild()
except Exception:
    pass
try:
    from app.schemas import CreditLineHistoryRead
    CreditLineHistoryRead.model_rebuild()
except Exception:
    pass
