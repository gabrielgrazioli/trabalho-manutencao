from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from silverstrike.models import Account, AccountType, Category, Transaction
from silverstrike.tests import create_transaction


class TransactionSearchTests(TestCase):
    """Busca de transações por texto e período (Etapa 6, critérios CA1 a CA7)."""

    def setUp(self):
        User.objects.create_superuser(username='admin', email='email@example.com', password='pass')
        self.client.login(username='admin', password='pass')
        self.personal = Account.objects.create(name='personal', show_on_dashboard=True)
        self.foreign = Account.objects.create(
            name='foreign account', account_type=AccountType.FOREIGN)
        self.food = Category.objects.create(name='food')
        self.fun = Category.objects.create(name='fun')

    def add(self, title, when=date(2026, 10, 15), category=None):
        return create_transaction(title, self.personal, self.foreign, 10,
                                  Transaction.WITHDRAW, when, category=category)

    def get(self, **params):
        response = self.client.get(reverse('transactions'), params)
        self.assertEqual(response.status_code, 200)
        return response

    def titles(self, **params):
        return [split.transaction.title for split in self.get(**params).context['transactions']]

    def test_without_parameters_lists_everything(self):
        self.add('Mercado Central')
        self.add('Padaria')
        self.assertCountEqual(self.titles(), ['Mercado Central', 'Padaria'])

    def test_text_search_ignores_case(self):
        self.add('Mercado Central')
        self.add('mercado livre')
        self.add('Padaria')
        self.assertCountEqual(self.titles(q='MERCADO'), ['Mercado Central', 'mercado livre'])

    def test_text_search_without_match_is_empty(self):
        self.add('Padaria')
        self.assertEqual(self.titles(q='zzz'), [])

    def test_period_is_inclusive(self):
        for day in (date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 15),
                    date(2026, 10, 31), date(2026, 11, 1)):
            self.add('t-' + day.isoformat(), day)
        self.assertCountEqual(self.titles(start='2026-10-01', end='2026-10-31'),
                              ['t-2026-10-01', 't-2026-10-15', 't-2026-10-31'])

    def test_only_start(self):
        self.add('antes', date(2026, 9, 30))
        self.add('depois', date(2026, 10, 1))
        self.assertEqual(self.titles(start='2026-10-01'), ['depois'])

    def test_only_end(self):
        self.add('antes', date(2026, 9, 30))
        self.add('depois', date(2026, 10, 1))
        self.assertEqual(self.titles(end='2026-09-30'), ['antes'])

    def test_text_and_category_are_combined(self):
        self.add('Mercado A', category=self.food)
        self.add('Mercado B', category=self.fun)
        self.add('Padaria', category=self.food)
        self.assertEqual(self.titles(q='mercado', category=self.food.id), ['Mercado A'])

    def test_text_and_period_are_combined(self):
        self.add('Mercado cedo', date(2026, 9, 1))
        self.add('Mercado tarde', date(2026, 10, 20))
        self.add('Padaria tarde', date(2026, 10, 20))
        self.assertEqual(self.titles(q='mercado', start='2026-10-01'), ['Mercado tarde'])

    def test_existing_category_filter_still_works(self):
        self.add('Mercado A', category=self.food)
        self.add('Mercado B', category=self.fun)
        self.assertEqual(self.titles(category=self.food.id), ['Mercado A'])

    def test_invalid_date_is_ignored(self):
        self.add('um')
        self.add('dois')
        self.assertCountEqual(self.titles(start='abc'), ['um', 'dois'])
        self.assertCountEqual(self.titles(end='2026-13-45'), ['um', 'dois'])

    def test_start_after_end_is_empty(self):
        self.add('um')
        self.assertEqual(self.titles(start='2026-12-01', end='2026-01-01'), [])

    def test_pagination_keeps_the_search(self):
        for number in range(51):
            self.add('mercado %02d' % number)
        self.add('Padaria')
        response = self.get(q='mercado')
        self.assertEqual(len(response.context['transactions']), 50)
        self.assertContains(response, '?q=mercado&amp;page=2')
        self.assertContains(response, 'q\\u003Dmercado&page=')
        second_page = self.get(q='mercado', page=2)
        self.assertEqual(len(second_page.context['transactions']), 1)

    def test_search_form_keeps_existing_filters(self):
        response = self.get(category=self.food.id, q='x')
        self.assertContains(
            response, '<input type="hidden" name="category" value="%s">' % self.food.id)
