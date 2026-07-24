from decimal import Decimal

from .models import FeeProfile

# 기본 프로필
DEFAULT_PROFILE = FeeProfile(
    marketplace="default",
    marketplace_fee_rate=Decimal("0.15"),
    payment_fee_rate=Decimal("0.03"),
    fixed_fee=Decimal("0.30"),
)

# eBay
EBAY_PROFILE = FeeProfile(
    marketplace="ebay",
    marketplace_fee_rate=Decimal("0.13"),
    payment_fee_rate=Decimal("0.03"),
    fixed_fee=Decimal("0.30"),
)

# Amazon
AMAZON_PROFILE = FeeProfile(
    marketplace="amazon",
    marketplace_fee_rate=Decimal("0.15"),
    payment_fee_rate=Decimal("0.03"),
    fixed_fee=Decimal("0.30"),
)

# 향후 Walmart, Etsy 등을 쉽게 추가할 수 있도록 dict 사용
FEE_PROFILES: dict[str, FeeProfile] = {
    "default": DEFAULT_PROFILE,
    "ebay": EBAY_PROFILE,
    "amazon": AMAZON_PROFILE,
}


def get_fee_profile(marketplace: str) -> FeeProfile:
    """
    마켓플레이스에 맞는 수수료 프로필을 반환한다.
    없으면 DEFAULT_PROFILE을 반환한다.
    """
    if marketplace is None:
        return DEFAULT_PROFILE

    return FEE_PROFILES.get(
        marketplace.strip().lower(),
        DEFAULT_PROFILE,
    )