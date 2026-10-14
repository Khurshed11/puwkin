from aiogram.fsm.state import State, StatesGroup


# ============ Добавление товара (админ) ============
class AddProduct(StatesGroup):
    category = State()       # выбор категории
    name = State()           # название товара
    photos = State()         # загрузка фото
    price = State()          # цена товара
    delivery_price = State() # цена доставки
    size_chart = State()     # шаблон замеров / наличия


# ============ Редактирование товара (админ) ============
class EditProduct(StatesGroup):
    waiting_new_price = State()
    waiting_new_delivery = State()
    waiting_new_name = State()
    waiting_new_desc = State()
    waiting_photos = State()      # дозагрузка фото
    waiting_new_category = State()  # смена категории


# ============ Настройки доставки (админ) ============
class DeliverySettings(StatesGroup):
    waiting_min_days = State()
    waiting_max_days = State()


# ============ Подбор размера (клиент) ============
class SizeHelper(StatesGroup):
    waiting_height = State()
    waiting_weight = State()


# ============ Оформление заказа (клиент) ============
class Checkout(StatesGroup):
    waiting_phone = State()
    waiting_address = State()


# ============ Поиск по каталогу (клиент) ============
class Search(StatesGroup):
    waiting_query = State()


# ============ Рассылка (админ) ============
class Broadcast(StatesGroup):
    waiting_content = State()   # текст/фото для рассылки


# ============ Промокоды (админ) ============
class PromoAdmin(StatesGroup):
    waiting_code = State()
    waiting_percent = State()


# ============ Отзыв (клиент) ============
class ReviewFSM(StatesGroup):
    waiting_rating = State()
    waiting_text = State()


# ============ FAQ — вопрос менеджеру (клиент) ============
class AskManager(StatesGroup):
    waiting_question = State()
