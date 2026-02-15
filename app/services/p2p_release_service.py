async def release_crypto_to_buyer(trade, release_token_amount=None, fee_token_amount=None):
    """
    Ici tu appelles :
    - soit ton escrow_service existant
    - soit tu fais transfert ERC20
    """

    # Exemple minimal (a remplacer par vrai transfert)
    amount = release_token_amount if release_token_amount is not None else trade.token_amount
    print(
        f"Releasing {amount} {trade.token} to buyer {trade.buyer_id}"
        + (f" (fee: {fee_token_amount})" if fee_token_amount is not None else "")
    )
