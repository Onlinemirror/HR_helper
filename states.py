from aiogram.fsm.state import State, StatesGroup


class AddEmployee(StatesGroup):
    last_name   = State()
    first_name  = State()
    middle_name = State()
    iin         = State()
    position    = State()
    city        = State()
    department  = State()
    confirm     = State()


class FireEmployee(StatesGroup):
    waiting_query = State()
    confirm       = State()


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
