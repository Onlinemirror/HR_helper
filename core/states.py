from aiogram.fsm.state import State, StatesGroup


class AddEmployee(StatesGroup):
    last_name     = State()
    first_name    = State()
    middle_name   = State()
    birth_date    = State()
    iin           = State()
    position      = State()
    city          = State()
    department    = State()
    contract_type = State()
    legal_entity  = State()
    phone         = State()
    email         = State()
    manager       = State()
    confirm       = State()


class FireEmployee(StatesGroup):
    waiting_query  = State()
    confirm        = State()
    waiting_date   = State()   # дата увольнения для приказа
    waiting_prikaz = State()   # номер приказа (авто или ручной)


class UploadDocument(StatesGroup):
    waiting_employee_query = State()
    waiting_doc_category   = State()   # выбор папки/категории документа
    waiting_file           = State()


class GenerateDocument(StatesGroup):
    waiting_employee   = State()   # ввод ИИН/ID
    waiting_prikaz_num = State()   # номер приказа (авто или ручной)
    waiting_extra      = State()   # доп. поля (динамически)
    confirm            = State()   # подтверждение


class DownloadEmployeeFiles(StatesGroup):
    waiting_employee = State()   # ввод ИИН/ID
    waiting_folder   = State()   # выбор папки


class EmployeeCard(StatesGroup):
    waiting_employee = State()
    waiting_select   = State()


class EditEmployee(StatesGroup):
    waiting_employee = State()
    waiting_select   = State()
    waiting_field    = State()
    waiting_value    = State()
    confirm          = State()


class Statistics(StatesGroup):
    menu = State()


class HRAddOnboarding(StatesGroup):
    """FSM добавления нового сотрудника на онбординг."""
    telegram_id  = State()   # Telegram ID сотрудника
    full_name    = State()   # ФИО (подтягивается автоматически, HR может исправить)
    position     = State()   # должность
    department   = State()   # отдел
    hr_sheet_id  = State()   # ID из Google Sheets (напр. ALA-001)
    start_date   = State()   # дата первого рабочего дня
    confirm      = State()   # подтверждение перед созданием


class HRProgressQuery(StatesGroup):
    """FSM запроса прогресса конкретного сотрудника."""
    waiting_id = State()


class Evaluate360(StatesGroup):
    waiting_employee   = State()
    score_quality      = State()
    score_teamwork     = State()
    score_initiative   = State()
    score_communication= State()
    score_knowledge    = State()
    waiting_strengths  = State()
    waiting_improve    = State()
    confirm            = State()
