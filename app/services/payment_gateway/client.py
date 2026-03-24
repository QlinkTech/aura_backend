from razorpay import Client
from razorpay.errors import BadRequestError, ServerError
from fastapi import HTTPException, status
from app.utils.env_load import razorpay_app_id, razorpay_app_secrete

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
        return gateway_client.subscription.fetch(subscription_id)
    except BadRequestError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except ServerError as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except Exception as e:
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

        return gateway_client.subscription.create(payload)
    except BadRequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ServerError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


def cancel_subscription(subscription_id: str, cancel_at_cycle_end: int = 0) -> dict:
    try:
        return gateway_client.subscription.cancel(subscription_id, {
            "cancel_at_cycle_end": cancel_at_cycle_end
        })
    except BadRequestError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ServerError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )