from datetime import date

from django.test import TestCase

from silverstrike.models import Account, AccountType, RecurringTransaction, Transaction


class UpdateDateTests(TestCase):
    """Testes de caracterização de RecurringTransaction.update_date.

    Registram o comportamento existente (antes da refatoração) para os ramos
    que os testes originais não exercitam: semanal, diário, multiplicador e
    tratamento de fim de semana.
    """

    def setUp(self):
        self.personal = Account.objects.create(name='personal')
        self.foreign = Account.objects.create(
            name='foreign', account_type=AccountType.FOREIGN)

    def make(self, start, interval, **kwargs):
        return RecurringTransaction.objects.create(
            title='recurrence', amount=10, date=start,
            src=self.personal, dst=self.foreign, interval=interval,
            transaction_type=Transaction.WITHDRAW, **kwargs)

    def test_weekly(self):
        r = self.make(date(2018, 1, 30), RecurringTransaction.WEEKLY)
        self.assertEqual(r.update_date(), date(2018, 2, 6))

    def test_daily(self):
        r = self.make(date(2018, 1, 30), RecurringTransaction.DAILY)
        self.assertEqual(r.update_date(), date(2018, 1, 31))

    def test_multiplier(self):
        r = self.make(date(2018, 1, 15), RecurringTransaction.MONTHLY, multiplier=2)
        self.assertEqual(r.update_date(), date(2018, 3, 15))

    def test_weekly_ignores_usual_month_day(self):
        r = self.make(date(2018, 1, 30), RecurringTransaction.WEEKLY, usual_month_day=15)
        self.assertEqual(r.update_date(), date(2018, 2, 6))

    def test_weekend_same_day(self):
        r = self.make(date(2018, 1, 3), RecurringTransaction.MONTHLY,
                      weekend_handling=RecurringTransaction.SAME_DAY)
        self.assertEqual(r.update_date(), date(2018, 2, 3))  # sábado

    def test_weekend_next_weekday_from_saturday(self):
        r = self.make(date(2018, 1, 3), RecurringTransaction.MONTHLY,
                      weekend_handling=RecurringTransaction.NEXT_WEEKDAY)
        self.assertEqual(r.update_date(), date(2018, 2, 5))  # segunda

    def test_weekend_next_weekday_from_sunday(self):
        r = self.make(date(2018, 1, 4), RecurringTransaction.MONTHLY,
                      weekend_handling=RecurringTransaction.NEXT_WEEKDAY)
        self.assertEqual(r.update_date(), date(2018, 2, 5))  # segunda

    def test_weekend_previous_weekday_from_saturday(self):
        r = self.make(date(2018, 1, 3), RecurringTransaction.MONTHLY,
                      weekend_handling=RecurringTransaction.PREVIOUS_WEEKDAY)
        self.assertEqual(r.update_date(), date(2018, 2, 2))  # sexta

    def test_weekend_previous_weekday_from_sunday(self):
        r = self.make(date(2018, 1, 4), RecurringTransaction.MONTHLY,
                      weekend_handling=RecurringTransaction.PREVIOUS_WEEKDAY)
        self.assertEqual(r.update_date(), date(2018, 2, 2))  # sexta

    def test_weekend_skip(self):
        r = self.make(date(2018, 1, 3), RecurringTransaction.MONTHLY,
                      weekend_handling=RecurringTransaction.SKIP)
        # 03/02 e 03/03 caem no sábado: pula até 03/04 (terça)
        self.assertEqual(r.update_date(), date(2018, 4, 3))

    def test_weekly_ignores_weekend_handling(self):
        r = self.make(date(2018, 1, 27), RecurringTransaction.WEEKLY,
                      weekend_handling=RecurringTransaction.NEXT_WEEKDAY)
        self.assertEqual(r.update_date(), date(2018, 2, 3))  # sábado, sem ajuste

    def test_without_save_does_not_persist(self):
        r = self.make(date(2018, 1, 30), RecurringTransaction.WEEKLY)
        new_date = r.update_date()
        self.assertEqual(new_date, date(2018, 2, 6))
        self.assertEqual(r.date, date(2018, 1, 30))

    def test_save_persists(self):
        r = self.make(date(2018, 1, 30), RecurringTransaction.WEEKLY)
        r.update_date(save=True)
        r.refresh_from_db()
        self.assertEqual(r.date, date(2018, 2, 6))
