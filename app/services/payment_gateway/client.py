from razorpay import Client
from razorpay.errors import BadRequestError, ServerError
from fastapi import HTTPException, status
from app.utils.env_load import razorpay_app_id, razorpay_app_secrete
from app.utils.logger_config import logger

APP_ID = razorpay_app_id
APP_SECRETE = razorpay_app_secrete

gateway_client = Client(auth=(APP_ID, APP_SECRETE))

# sub_plans = {
#     "3_months_plan" : "plan_SSgpJOIP16Ajnt",
#     "1_year_plan" : "plan_SHezS2mVAAsmvy"
# }

sub_plans = {
    "3_months_plan" : {
        "id": "plan_SSgpJOIP16Ajnt",
        "total_count" : 40
    },
    "1_year_plan" : {
        "id": "plan_SHezS2mVAAsmvy",
        "total_count" : 10
    }
}


def fetch_subscription(subscription_id: str) -> dict:
    try:
        logger.info("Fetching subscription from Razorpay", extra={"subscription_id": subscription_id})
        result = gateway_client.subscription.fetch(subscription_id)
        logger.info("Subscription fetched", extra={"subscription_id": subscription_id, "status": result.get("status")})
        return result
    except BadRequestError as e:
        logger.error("Razorpay bad request on fetch_subscription", extra={"subscription_id": subscription_id, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ServerError as e:
        logger.error("Razorpay server error on fetch_subscription", extra={"subscription_id": subscription_id, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except Exception as e:
        logger.error("Unexpected error on fetch_subscription", extra={"subscription_id": subscription_id, "error": str(e)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


def create_subscription(plan_key: str, notify_email: str, expire_by: int = None, start_at: int = None, notify_phone: str = None, quantity: int = 1) -> dict:
    if plan_key not in sub_plans:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plan key: {plan_key}"
        )
    try:
        notify_info = {"notify_email": notify_email}
        if notify_phone:
            notify_info["notify_phone"] = notify_phone

        payload = {
            "plan_id": sub_plans[plan_key]["id"],
            "total_count": sub_plans[plan_key]["total_count"],
            "quantity": quantity,
            "customer_notify": True,
            "notify_info": notify_info,
        }
        if expire_by is not None:
            payload["expire_by"] = expire_by
        if start_at is not None:
            payload["start_at"] = start_at

        logger.info("Creating Razorpay subscription", extra={"plan_key": plan_key, "notify_email": notify_email, "start_at": start_at, "expire_by": expire_by})
        result = gateway_client.subscription.create(payload)
        logger.info("Razorpay subscription created", extra={"subscription_id": result.get("id"), "plan_key": plan_key})
        return result
    except BadRequestError as e:
        logger.error("Razorpay bad request on create_subscription", extra={"plan_key": plan_key, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ServerError as e:
        logger.error("Razorpay server error on create_subscription", extra={"plan_key": plan_key, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Unexpected error on create_subscription", extra={"plan_key": plan_key, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


def cancel_subscription(subscription_id: str, cancel_at_cycle_end: int = 0) -> dict:
    try:
        logger.info("Cancelling Razorpay subscription", extra={"subscription_id": subscription_id, "cancel_at_cycle_end": cancel_at_cycle_end})
        result = gateway_client.subscription.cancel(subscription_id, {
            "cancel_at_cycle_end": cancel_at_cycle_end
        })
        logger.info("Razorpay subscription cancelled", extra={"subscription_id": subscription_id})
        return result
    except BadRequestError as e:
        logger.error("Razorpay bad request on cancel_subscription", extra={"subscription_id": subscription_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ServerError as e:
        logger.error("Razorpay server error on cancel_subscription", extra={"subscription_id": subscription_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)
        )
    except Exception as e:
        logger.error("Unexpected error on cancel_subscription", extra={"subscription_id": subscription_id, "error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
