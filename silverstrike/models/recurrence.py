from datetime import date

from dateutil.relativedelta import relativedelta

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext as _

from .account import Account
from .category import Category
from .transaction import Split, Transaction
from ..lib import last_day_of_month


class RecurringTransactionManager(models.Manager):
    def due_in_month(self, month=None):
        if not month:
            month = date.today()
        month = last_day_of_month(month)
        queryset = self.get_queryset().filter(date__lte=month)
        return queryset.exclude(interval=RecurringTransaction.DISABLED)


class RecurringTransaction(models.Model):
    DISABLED = 0
    MONTHLY = 1
    QUARTERLY = 2
    BIANNUALLY = 3
    ANNUALLY = 4
    WEEKLY = 5
    DAILY = 6

    RECCURENCE_OPTIONS = (
        (DISABLED, _('Disabled')),
        (DAILY, _('Daily')),
        (WEEKLY, _('Weekly')),
        (MONTHLY, _('Monthly')),
        (QUARTERLY, _('Quarterly')),
        (BIANNUALLY, _('Biannually')),
        (ANNUALLY, _('Annually'))
        )

    SAME_DAY = 0
    PREVIOUS_WEEKDAY = 1
    NEXT_WEEKDAY = 2
    SKIP = 3

    WEEKEND_SKIPPING = (
        (SKIP, _('Skip recurrence')),
        (SAME_DAY, _('Same day')),
        (PREVIOUS_WEEKDAY, _('Previous weekday')),
        (NEXT_WEEKDAY, _('Next weekday'))
    )

    # Quanto avançar a data em cada intervalo (multiplicado por `multiplier`)
    INTERVAL_DELTAS = {
        MONTHLY: {'months': 1},
        QUARTERLY: {'months': 3},
        BIANNUALLY: {'months': 6},
        ANNUALLY: {'years': 1},
        WEEKLY: {'weeks': 1},
        DAILY: {'days': 1},
    }
    FRIDAY = 4  # date.weekday(): segunda=0 ... sexta=4, sábado=5, domingo=6
    DAYS_IN_WEEK = 7

    class Meta:
        ordering = ['date']

    objects = RecurringTransactionManager()

    title = models.CharField(max_length=64)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    usual_month_day = models.PositiveIntegerField(default=0)
    date = models.DateField()
    src = models.ForeignKey(Account, models.CASCADE)
    dst = models.ForeignKey(Account, models.CASCADE,
                            related_name='opposing_recurring_transactions')
    interval = models.IntegerField(choices=RECCURENCE_OPTIONS)
    transaction_type = models.IntegerField(choices=Transaction.TRANSACTION_TYPES[:3])
    category = models.ForeignKey(Category, models.SET_NULL, null=True, blank=True)
    last_modified = models.DateTimeField(auto_now=True)

    multiplier = models.PositiveIntegerField(default=1)
    weekend_handling = models.IntegerField(default=SAME_DAY, choices=WEEKEND_SKIPPING)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('recurrence_detail', args=[self.pk])

    @property
    def is_due(self):
        return date.today() >= self.date

    def update_date(self, date=None, save=False):
        """
        Calculates the date to the next occurence and optionally saves it.
        It uses the usual_month_day if set for setting the correct day in a monthly recurrence
        """
        delta = self._get_delta()
        if delta is None:
            return
        if not date:
            date = self.date
        while True:
            date += delta
            date = self._with_usual_month_day(date)
            if self._is_skipped_weekend(date):
                continue
            date = self._shift_weekend(date)
            if save:
                self.date = date
                self.save()
            return date

    @property
    def _follows_calendar_rules(self):
        """Only monthly or longer intervals use usual_month_day and weekend handling."""
        return self.interval not in (self.WEEKLY, self.DAILY)

    def _get_delta(self):
        """Interval between two occurrences, or None if the recurrence is disabled."""
        delta_args = self.INTERVAL_DELTAS.get(self.interval)
        if delta_args is None:
            return None
        return relativedelta(**delta_args) * self.multiplier

    def _with_usual_month_day(self, candidate):
        """Moves candidate to usual_month_day, using the month's last day if it is shorter."""
        if self.usual_month_day <= 0 or not self._follows_calendar_rules:
            return candidate
        day = self.usual_month_day
        while True:
            try:
                return candidate.replace(day=day)
            except ValueError:
                day -= 1

    def _is_weekend(self, candidate):
        return self._follows_calendar_rules and candidate.weekday() > self.FRIDAY

    def _is_skipped_weekend(self, candidate):
        return self._is_weekend(candidate) and self.weekend_handling == self.SKIP

    def _shift_weekend(self, candidate):
        """Moves a weekend candidate to the next or previous weekday, if so configured."""
        if not self._is_weekend(candidate):
            return candidate
        if self.weekend_handling == self.NEXT_WEEKDAY:
            return candidate + relativedelta(days=self.DAYS_IN_WEEK - candidate.weekday())
        if self.weekend_handling == self.PREVIOUS_WEEKDAY:
            return candidate - relativedelta(days=candidate.weekday() - self.FRIDAY)
        return candidate

    @property
    def is_disabled(self):
        return self.interval == self.DISABLED

    @property
    def get_recurrence(self):
        for r, name in self.RECCURENCE_OPTIONS:
            if r == self.interval:
                return name

    @property
    def signed_amount(self):
        if self.transaction_type == Transaction.WITHDRAW:
            return -self.amount
        else:
            return self.amount

    @property
    def is_withdraw(self):
        return self.transaction_type == Transaction.WITHDRAW

    @property
    def is_deposit(self):
        return self.transaction_type == Transaction.DEPOSIT

    @property
    def average_amount(self):
        average = Split.objects.personal().recurrence(self.id).aggregate(
            models.Avg('amount'))['amount__avg']
        if not average:
            return '—'
        return round(average, 2)

    @classmethod
    def outstanding_transaction_sum(cls):
        from .lib import last_day_of_month
        outstanding = 0
        dend = last_day_of_month(date.today())
        transactions = cls.objects.due_in_month().exclude(
            transaction_type=Transaction.TRANSFER)
        for t in transactions:
            while t.date <= dend:
                if t.transaction_type == Transaction.WITHDRAW:
                    outstanding -= t.amount
                else:
                    outstanding += t.amount
                t.update_date()
        return outstanding
