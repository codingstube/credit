from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Float, String, Date, Integer
from datetime import datetime, date, timedelta
import math

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///loans.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key_here'
db = SQLAlchemy(app)

class Base(DeclarativeBase):
    pass

class Loan(db.Model):
    __tablename__ = 'loans'

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    principal: Mapped[float] = mapped_column(Float, nullable=False)
    interest_rate: Mapped[float] = mapped_column(Float, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_payment: Mapped[float] = mapped_column(Float, nullable=False)
    initial_capital: Mapped[float] = mapped_column(Float, default=0.0)  # Neues Feld

    def calculate_remaining_balance(self):
        today = date.today()
        months_elapsed = (today.year - self.start_date.year) * 12 + (today.month - self.start_date.month)
        if months_elapsed >= self.term_months:
            return 0.0
        monthly_rate = self.interest_rate / 12 / 100
        remaining_payments = self.term_months - months_elapsed
        remaining_balance = (self.monthly_payment * ((1 - (1 + monthly_rate) ** -remaining_payments) / monthly_rate))
        return round(max(0.0, remaining_balance), 2)

    def calculate_end_date(self):
        end_date = self.start_date + timedelta(days=(self.term_months * 30.44))
        return end_date.strftime('%d.%m.%Y')

    def months_remaining(self):
        today = date.today()
        months_elapsed = (today.year - self.start_date.year) * 12 + (today.month - self.start_date.month)
        return max(0, self.term_months - months_elapsed)

    def calculate_total_interest(self):
        """Calculate the total interest to be paid over the lifetime of the loan."""
        total_payment = self.monthly_payment * self.term_months
        total_interest = total_payment - self.principal
        return round(total_interest, 2)

    def calculate_remaining_interest(self):
        """Calculate the remaining interest to be paid."""
        total_interest = self.calculate_total_interest()
        months_paid = (date.today().year - self.start_date.year) * 12 + \
                    (date.today().month - self.start_date.month)
        interest_paid = (total_interest / self.term_months) * months_paid
        return round(max(0.0, total_interest - interest_paid), 2)
    
    def calculate_interest_only_months(self):
        """Calculate how many months are interest-only (if monthly payment equals or is less than interest)."""
        monthly_interest = (self.principal * (self.interest_rate / 12 / 100))
        if self.monthly_payment <= monthly_interest:
            return self.term_months  # Entire term is interest-only
        return 0  # Directly starts reducing principal

    def calculate_remaining_principal(self):
        """Calculate the remaining principal after all interest is paid."""
        total_remaining_balance = self.calculate_remaining_balance()
        remaining_interest = self.calculate_remaining_interest()
        return round(total_remaining_balance - remaining_interest, 2) 



# Function to format currency
def format_currency(value):
    """Format a number as currency in German style with € at the end."""
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"

app.jinja_env.filters['format_currency'] = format_currency  

def format_decimal(value):
    """Format a float to use a comma as a decimal separator."""
    return str(value).replace('.', ',')

app.jinja_env.filters['format_decimal'] = format_decimal

# Create database tables
with app.app_context():
    db.create_all()


@app.route('/')
def index():
    loans = Loan.query.all()
    total_principal = sum(loan.principal for loan in loans)
    total_monthly_payment = sum(loan.monthly_payment for loan in loans)
    total_remaining_balance = sum(loan.calculate_remaining_balance() for loan in loans)

    return render_template('index.html', 
                           loans=loans, 
                           total_principal=total_principal,
                           total_monthly_payment=total_monthly_payment,
                           total_remaining_balance=total_remaining_balance)


@app.route('/add_loan', methods=['GET', 'POST'])
def add_loan():
    if request.method == 'POST':
        def to_float(value):
            """Convert comma-based decimal input to float."""
            return float(value.replace(',', '.'))

        principal = to_float(request.form['principal'])
        interest_rate = to_float(request.form['interest_rate'])
        initial_capital = to_float(request.form.get('initial_capital', '0'))
        monthly_payment = request.form.get('monthly_payment')
        term_months = request.form.get('term_months')

        # Effektiver Kreditbetrag nach Abzug des Startkapitals
        adjusted_principal = principal - initial_capital
        if adjusted_principal < 0:
            adjusted_principal = 0.0

        # Monatlicher Zinssatz
        monthly_rate = interest_rate / 12 / 100

        # Berechnung basierend auf den Eingaben
        if monthly_payment:
            # Monatliche Rate ist angegeben, Laufzeit wird berechnet
            monthly_payment = to_float(monthly_payment)
            if monthly_payment <= adjusted_principal * monthly_rate:
                term_months = float('inf')  # Unendliche Laufzeit
            else:
                term_months = math.log(
                    monthly_payment / (monthly_payment - adjusted_principal * monthly_rate)
                ) / math.log(1 + monthly_rate)
            term_months = int(round(term_months))
        elif term_months:
            # Laufzeit ist angegeben, monatliche Rate wird berechnet
            term_months = int(term_months)
            monthly_payment = adjusted_principal * (monthly_rate * (1 + monthly_rate)**term_months) / \
                              ((1 + monthly_rate)**term_months - 1)
        else:
            # Fehler, wenn weder monatliche Rate noch Laufzeit angegeben ist
            return "Bitte geben Sie entweder die Laufzeit oder die monatliche Rate an.", 400

        # Kredit speichern
        loan = Loan(
            name=request.form['name'],
            principal=principal,
            interest_rate=interest_rate,
            start_date=datetime.strptime(request.form['start_date'], '%Y-%m-%d').date(),
            term_months=term_months,
            monthly_payment=round(monthly_payment, 2),
            initial_capital=initial_capital
        )
        db.session.add(loan)
        db.session.commit()
        return redirect(url_for('index'))

    return render_template('add_loan.html')

@app.route('/edit_loan/<int:id>', methods=['GET', 'POST'])
def edit_loan(id):
    loan = Loan.query.get_or_404(id)

    if request.method == 'POST':
        def to_float(value):
            """Convert comma-based decimal input to float."""
            return float(value.replace(',', '.'))

        loan.name = request.form['name']
        loan.principal = to_float(request.form['principal'])
        loan.initial_capital = to_float(request.form.get('initial_capital', '0'))
        loan.interest_rate = to_float(request.form['interest_rate'])
        loan.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()

        monthly_payment = request.form.get('monthly_payment')
        term_months = request.form.get('term_months')
        adjusted_principal = loan.principal - loan.initial_capital
        monthly_rate = loan.interest_rate / 12 / 100

        if monthly_payment:
            monthly_payment = to_float(monthly_payment)
            if monthly_payment <= adjusted_principal * monthly_rate:
                term_months = float('inf')
            else:
                term_months = math.log(
                    monthly_payment / (monthly_payment - adjusted_principal * monthly_rate)
                ) / math.log(1 + monthly_rate)
            loan.term_months = int(round(term_months))
            loan.monthly_payment = monthly_payment
        elif term_months:
            term_months = int(term_months)
            loan.term_months = term_months
            loan.monthly_payment = adjusted_principal * (monthly_rate * (1 + monthly_rate)**term_months) / \
                                   ((1 + monthly_rate)**term_months - 1)

        db.session.commit()
        return redirect(url_for('index'))

    return render_template('edit_loan.html', loan=loan)

@app.route('/delete_loan/<int:id>', methods=['POST'])
def delete_loan(id):
    loan = Loan.query.get_or_404(id)
    db.session.delete(loan)
    db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
