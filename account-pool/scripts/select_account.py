from core.storage import init_db
from core.selector import select_best_account

if __name__ == '__main__':
    init_db()
    account = select_best_account()
    if not account:
        print('NO_ACCOUNT')
    else:
        print(account)
