/** Brand name and contact. Change them here and the whole site follows. */
export const SITE_NAME = "Craftline";
export const SITE_TAGLINE = "Tell us what you need and get an estimate in about a minute.";
export const SUPPORT_EMAIL = process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "";

export const CURRENCY = "usd";

/**
 * Launch pricing. While true, estimates carry a "Launch pricing" label and the
 * home page mentions it. The lower prices themselves live in services.ts. When
 * the launch period ends, raise the amounts there and set this to false.
 */
export const LAUNCH_PRICING = true;
/** No order can be priced above this. Bigger jobs get no automatic estimate and are priced by hand. */
export const MAX_ORDER_CENTS = 2000_00;
/** Lowest price an order can be set to. */
export const MIN_ORDER_CENTS = 5_00;
