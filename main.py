import sys
import os
import shutil
import random
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox, QListWidgetItem, QFileDialog
from PySide6.QtUiTools import QUiLoader
from PySide6.QtGui import QPixmap, QFont, QIcon, QColor, QImageReader, QImage
from PySide6.QtCore import Qt, QDate, QObject, QEvent
from db import Database

class ClickFilter(QObject):
    def __init__(self, order_id, callback):
        super().__init__()
        self.order_id = order_id
        self.callback = callback

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            self.callback(self.order_id)
            return True
        return False

class ShoeStoreApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.user = None
        self.loader = QUiLoader()

        # Переменные для редактирования
        self.current_product_id = None
        self.current_photo_path = "picture.png"
        self.current_order_id = None

        # ЗАГРУЗКА ВСЕХ ОКОН
        self.w_auth = self.loader.load('ui/login.ui') # Авторизация
        self.w_main = self.loader.load('ui/main.ui')  # Главное окно

        # Всплывающие виджеты
        self.w_product_form = self.loader.load('ui/product_form.ui')
        self.w_order_list = self.loader.load('ui/orders_list.ui')
        self.w_order_form = self.loader.load('ui/order_form.ui')

        # ЗАЩИТА ОТ ОТКРЫТИЯ НЕСКОЛЬКИХ ОКОН
        self.w_product_form.setWindowModality(Qt.ApplicationModal)
        self.w_order_list.setWindowModality(Qt.ApplicationModal)
        self.w_order_form.setWindowModality(Qt.ApplicationModal)

        # НАСТРОЙКА КАЛЕНДАРЕЙ ДЛЯ ЗАКАЗОВ
        if hasattr(self.w_order_form, 'dateEdit') and hasattr(self.w_order_form, 'dateEdit_2'):
            # Включаем выпадающий календарь
            self.w_order_form.dateEdit.setCalendarPopup(True)
            self.w_order_form.dateEdit_2.setCalendarPopup(True)
            # Дата доставки не может быть раньше даты заказа
            self.w_order_form.dateEdit.dateChanged.connect(
                lambda date: self.w_order_form.dateEdit_2.setMinimumDate(date)
            )

        # СТИЛИ
        QApplication.setFont(QFont("Times New Roman", 12))
        icon_path = "import/Icon.png" if os.path.exists("import/Icon.png") else "import/picture.png"
        app_icon = QIcon(icon_path)
        self.w_auth.setWindowIcon(app_icon)
        self.w_main.setWindowIcon(app_icon)

        if hasattr(self.w_auth, 'lblLogoAuth'):
            self.w_auth.lblLogoAuth.setPixmap(QPixmap(icon_path).scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        global_style = """
            QWidget { background-color: #FFFFFF; color: black; }
            QListWidget, QScrollArea { border: 1px solid #cccccc; }
            QPushButton { background-color: #00FA9A; color: black; border: 1px solid black; border-radius: 4px; padding: 6px; font-weight: bold; }
            QPushButton:hover { background-color: #7FFF00; }
            QLineEdit, QComboBox, QTextEdit, QSpinBox, QDoubleSpinBox, QDateEdit { border: 1px solid #777777; padding: 4px; border-radius: 2px;}
        """
        for window in [self.w_auth, self.w_main, self.w_product_form, self.w_order_list, self.w_order_form]:
            window.setStyleSheet(global_style)

        # ПРИВЯЗКА СИГНАЛОВ
        self.w_auth.btnLogin.clicked.connect(self.login)
        self.w_auth.btnGuest.clicked.connect(self.login_guest)
        self.w_main.btnOut.clicked.connect(self.logout)

        # Навигация (Админ/Менеджер)
        if hasattr(self.w_main, 'btnAdd'): self.w_main.btnAdd.clicked.connect(self.open_add_product)
        if hasattr(self.w_main, 'btnOrders'): self.w_main.btnOrders.clicked.connect(self.open_orders_list)
        if hasattr(self.w_main, 'btnOrders_2'): self.w_main.btnOrders_2.clicked.connect(self.open_orders_list)

        # Фильтры Менеджера
        if hasattr(self.w_main, 'searchEdit'): self.w_main.searchEdit.textChanged.connect(self.load_products)
        if hasattr(self.w_main, 'comboSort'): self.w_main.comboSort.currentIndexChanged.connect(self.load_products)
        if hasattr(self.w_main, 'comboSupplier'): self.w_main.comboSupplier.currentIndexChanged.connect(self.load_products)

        # Фильтры Админа
        if hasattr(self.w_main, 'searchEdit_2'): self.w_main.searchEdit_2.textChanged.connect(self.load_products)
        if hasattr(self.w_main, 'comboSort_2'): self.w_main.comboSort_2.currentIndexChanged.connect(self.load_products)
        if hasattr(self.w_main, 'comboSupplier_2'): self.w_main.comboSupplier_2.currentIndexChanged.connect(self.load_products)

        # Кнопки формы товара
        self.w_product_form.btnBack.clicked.connect(self.w_product_form.close)
        self.w_product_form.btnLoadImage.clicked.connect(self.load_image)
        self.w_product_form.btnSaveProduct.clicked.connect(self.save_product)
        if hasattr(self.w_product_form, 'btnDelete'):
            self.w_product_form.btnDelete.clicked.connect(self.delete_product)

        # Кнопки формы заказов
        self.w_order_list.btnBack.clicked.connect(self.w_order_list.close)
        self.w_order_list.btnAddOrder.clicked.connect(self.open_add_order)

        self.w_order_form.btnBack.clicked.connect(self.w_order_form.close)
        self.w_order_form.btnSaveOrder.clicked.connect(self.save_order)
        self.w_order_form.btnDeleteOrder.clicked.connect(self.delete_order)

        self.w_auth.show()

    # АВТОРИЗАЦИЯ И УПРАВЛЕНИЕ РОЛЯМИ
    def login(self):
        query = "SELECT u.user_id, u.full_name, r.name as role FROM users u JOIN roles r ON u.role_id = r.role_id WHERE u.login=%s AND u.user_password=%s"
        user = self.db.fetch_one(query, (self.w_auth.lineLogin.text(), self.w_auth.linePassword.text()))
        if user:
            self.user = user
            self.open_main()
        else:
            QMessageBox.warning(self.w_auth, "Ошибка", "Неверный логин или пароль.")

    def login_guest(self):
        self.user = {'user_id': None, 'full_name': 'Гость', 'role': 'Гость'}
        self.open_main()

    def logout(self):
        self.user = None
        for w in [self.w_main, self.w_product_form, self.w_order_list, self.w_order_form]: w.close()
        self.w_auth.lineLogin.clear()
        self.w_auth.linePassword.clear()
        self.w_auth.show()

    def open_main(self):
        self.w_auth.close()

        role = self.user['role'].strip()
        self.w_main.lblUser.setText(f"{self.user['full_name']} ({role})")

        if role == 'Гость':
            self.w_main.stackedWidget.setCurrentWidget(self.w_main.page_guest)
        elif role == 'Менеджер':
            self.w_main.stackedWidget.setCurrentWidget(self.w_main.page_manager)
            self.populate_supplier_filter(self.w_main.comboSupplier)
        elif role == 'Администратор':
            self.w_main.stackedWidget.setCurrentWidget(self.w_main.page_admin)
            self.populate_supplier_filter(self.w_main.comboSupplier_2)
            try: self.w_main.listWidget_4.itemClicked.disconnect()
            except: pass
            self.w_main.listWidget_4.itemClicked.connect(self.open_edit_product)
        elif role == 'Авторизированный клиент':
            self.w_main.stackedWidget.setCurrentWidget(self.w_main.page_client)

        self.load_products()
        self.w_main.show()

    def populate_supplier_filter(self, combo):
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Все поставщики")
        for s in self.db.fetch_all("SELECT name FROM suppliers ORDER BY name"):
            combo.addItem(s['name'])
        combo.blockSignals(False)

    # КАТАЛОГ ТОВАРОВ И ФИЛЬТРЫ
    def load_products(self):
        role = self.user['role'].strip()
        search, sort_order, selected_supplier = "%%", "ASC", "Все поставщики"

        if role == 'Гость':
            current_list = self.w_main.listWidget
        elif role == 'Авторизированный клиент':
            current_list = self.w_main.listWidget_2
        elif role == 'Менеджер':
            current_list = self.w_main.listWidget_3
            search = f"%{self.w_main.searchEdit.text()}%"
            sort_order = "ASC" if self.w_main.comboSort.currentIndex() == 0 else "DESC"
            selected_supplier = self.w_main.comboSupplier.currentText()
        elif role == 'Администратор':
            current_list = self.w_main.listWidget_4
            search = f"%{self.w_main.searchEdit_2.text()}%"
            sort_order = "ASC" if self.w_main.comboSort_2.currentIndex() == 0 else "DESC"
            selected_supplier = self.w_main.comboSupplier_2.currentText()
        else:
            return

        current_list.clear()

        query = """
            SELECT p.*, m.name as manufacturer, s.name as supplier, c.name as category, un.name as unit
            FROM products p
            LEFT JOIN manufacturers m ON p.manufacturer_id = m.manufacturer_id
            LEFT JOIN suppliers s ON p.supplier_id = s.supplier_id
            LEFT JOIN categories c ON p.category_id = c.category_id
            LEFT JOIN units un ON p.unit_id = un.unit_id
            WHERE (p.product_name ILIKE %s OR p.description ILIKE %s OR c.name ILIKE %s)
        """
        params = [search, search, search]
        if selected_supplier != "Все поставщики":
            query += " AND s.name = %s"
            params.append(selected_supplier)

        query += f" ORDER BY p.stock_quantity {sort_order}"
        products = self.db.fetch_all(query, tuple(params))

        for p in products:
            item_widget = self.loader.load('ui/product_item.ui')
            item_widget.lblTitle.setText(f"{p['category']} | {p['product_name']}")
            item_widget.lblDesc.setText(f"Описание: {p['description']}")
            item_widget.lblManuf.setText(f"Производитель: {p['manufacturer']}")
            item_widget.lblSupplier.setText(f"Поставщик: {p['supplier']}")
            item_widget.lblUnit.setText(f"Ед. измерения: {p['unit']}")

            if p['stock_quantity'] == 0:
                item_widget.lblStock.setText(f"<span style='background-color: lightblue;'>Остаток: 0</span>")
            else:
                item_widget.lblStock.setText(f"Остаток: {p['stock_quantity']}")

            if p['discount'] > 0:
                final_price = float(p['price']) * (1 - float(p['discount']) / 100)
                item_widget.lblPrice.setText(f"Цена: <s><font color='red'>{p['price']}</font></s> {final_price:.2f} руб.")
                item_widget.lblDiscount.setText(f"<b>Скидка: {p['discount']}%</b>")
            else:
                item_widget.lblPrice.setText(f"Цена: {p['price']} руб.")
                item_widget.lblDiscount.setText("")

            photo_path = f"import/{p['photo']}" if p['photo'] else "import/picture.png"
            if not os.path.exists(photo_path): photo_path = "import/picture.png"
            item_widget.lblImage.setPixmap(QPixmap(photo_path).scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))

            item = QListWidgetItem(current_list)
            item.setSizeHint(item_widget.sizeHint())
            item.setData(Qt.UserRole, p['id'])

            if p['discount'] >= 15:
                item.setBackground(QColor("#2E8B57"))
                item_widget.setStyleSheet("background: transparent; color: white;")
            else:
                item.setBackground(QColor("#FFFFFF"))
                item_widget.setStyleSheet("background: transparent; color: black;")

            current_list.addItem(item)
            current_list.setItemWidget(item, item_widget)

    # УПРАВЛЕНИЕ ТОВАРАМИ
    def populate_product_combos(self):
        self.w_product_form.comboCategory.clear()
        self.w_product_form.comboManuf.clear()
        self.w_product_form.comboSupplierForm.clear()
        self.w_product_form.comboUnit.clear()
        for c in self.db.fetch_all("SELECT name FROM categories"): self.w_product_form.comboCategory.addItem(c['name'])
        for m in self.db.fetch_all("SELECT name FROM manufacturers"): self.w_product_form.comboManuf.addItem(m['name'])
        for s in self.db.fetch_all("SELECT name FROM suppliers"): self.w_product_form.comboSupplierForm.addItem(s['name'])
        for u in self.db.fetch_all("SELECT name FROM units"): self.w_product_form.comboUnit.addItem(u['name'])

    def open_add_product(self):
        self.current_product_id = None
        self.current_photo_path = "picture.png"
        self.w_product_form.setWindowTitle("Добавление товара")

        if hasattr(self.w_product_form, 'btnDelete'):
            self.w_product_form.btnDelete.setVisible(False)

        if hasattr(self.w_product_form, 'lineId'):
            self.w_product_form.lineId.setVisible(False)

        self.populate_product_combos()
        self.w_product_form.lineName.clear()
        self.w_product_form.textDesc.clear()
        self.w_product_form.spinPrice.setValue(0)
        self.w_product_form.spinStock.setValue(0)
        self.w_product_form.spinDiscount.setValue(0)
        self.w_product_form.lblPhoto.setPixmap(QPixmap("import/picture.png").scaled(300, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.w_product_form.show()

    def open_edit_product(self, item):
        self.current_product_id = item.data(Qt.UserRole)
        self.w_product_form.setWindowTitle("Редактирование товара")

        if hasattr(self.w_product_form, 'btnDelete'):
            self.w_product_form.btnDelete.setVisible(True)

        if hasattr(self.w_product_form, 'lineId'):
            self.w_product_form.lineId.setVisible(True)
            self.w_product_form.lineId.setReadOnly(True)
            self.w_product_form.lineId.setText(str(self.current_product_id))

        self.populate_product_combos()
        product = self.db.fetch_one("""
            SELECT p.*, c.name as cat, m.name as man, s.name as sup, u.name as unit 
            FROM products p 
            LEFT JOIN categories c ON p.category_id = c.category_id 
            LEFT JOIN manufacturers m ON p.manufacturer_id = m.manufacturer_id 
            LEFT JOIN suppliers s ON p.supplier_id = s.supplier_id 
            LEFT JOIN units u ON p.unit_id = u.unit_id 
            WHERE p.id = %s""", (self.current_product_id,))

        self.w_product_form.lineName.setText(product['product_name'])
        self.w_product_form.textDesc.setText(product['description'])
        self.w_product_form.spinPrice.setValue(float(product['price']))
        self.w_product_form.spinStock.setValue(product['stock_quantity'])
        self.w_product_form.spinDiscount.setValue(float(product['discount']))
        self.w_product_form.comboCategory.setCurrentText(product['cat'])
        self.w_product_form.comboManuf.setCurrentText(product['man'])
        self.w_product_form.comboSupplierForm.setCurrentText(product['sup'])
        self.w_product_form.comboUnit.setCurrentText(product['unit'])

        self.current_photo_path = product['photo'] if product['photo'] else "picture.png"
        path = f"import/{self.current_photo_path}"
        if not os.path.exists(path): path = "import/picture.png"
        self.w_product_form.lblPhoto.setPixmap(QPixmap(path).scaled(300, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.w_product_form.show()

    def load_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выбрать фото", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if file_path:
            try:
                image = QImage(file_path)
                if image.isNull():
                    return QMessageBox.warning(self.w_product_form, "Ошибка", "Не удалось прочитать изображение.")

                # Масштабируем без искажений пропорций с максимальным качеством (сглаживание)
                scaled_image = image.scaled(300, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                # Принудительно сохраняем в JPG
                base_name = os.path.splitext(os.path.basename(file_path))[0]
                new_filename = f"{base_name}.jpg"
                dest = os.path.join("import", new_filename)

                scaled_image.save(dest, "JPG", 100)
                self.current_photo_path = new_filename
                self.w_product_form.lblPhoto.setPixmap(QPixmap.fromImage(scaled_image))
            except Exception as e:
                QMessageBox.critical(self.w_product_form, "Ошибка", f"Не удалось обработать фото:\n{str(e)}")

    def save_product(self):
        name = self.w_product_form.lineName.text().strip()
        if not name: return QMessageBox.warning(self.w_product_form, "Внимание", "Название пустое.")

        c_id = self.db.fetch_one("SELECT category_id FROM categories WHERE name=%s", (self.w_product_form.comboCategory.currentText(),))['category_id']
        m_id = self.db.fetch_one("SELECT manufacturer_id FROM manufacturers WHERE name=%s", (self.w_product_form.comboManuf.currentText(),))['manufacturer_id']
        s_id = self.db.fetch_one("SELECT supplier_id FROM suppliers WHERE name=%s", (self.w_product_form.comboSupplierForm.currentText(),))['supplier_id']
        u_id = self.db.fetch_one("SELECT unit_id FROM units WHERE name=%s", (self.w_product_form.comboUnit.currentText(),))['unit_id']

        try:
            if self.current_product_id is None:
                next_id = self.db.fetch_one("SELECT COALESCE(MAX(id), 0) + 1 as new_id FROM products")['new_id']
                self.db.execute_query("""
                    INSERT INTO products (article, product_name, description, price, discount, stock_quantity, photo, category_id, manufacturer_id, supplier_id, unit_id) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                                      (f"ART-{next_id}", name, self.w_product_form.textDesc.text(), self.w_product_form.spinPrice.value(), self.w_product_form.spinDiscount.value(), self.w_product_form.spinStock.value(), self.current_photo_path, c_id, m_id, s_id, u_id))
            else:
                self.db.execute_query("""
                    UPDATE products SET product_name=%s, description=%s, price=%s, discount=%s, stock_quantity=%s, photo=%s, category_id=%s, manufacturer_id=%s, supplier_id=%s, unit_id=%s WHERE id=%s""",
                                      (name, self.w_product_form.textDesc.text(), self.w_product_form.spinPrice.value(), self.w_product_form.spinDiscount.value(), self.w_product_form.spinStock.value(), self.current_photo_path, c_id, m_id, s_id, u_id, self.current_product_id))

            QMessageBox.information(self.w_product_form, "Успех", "Сохранено!")
            self.load_products()
            self.w_product_form.close()
        except Exception as e:
            QMessageBox.critical(self.w_product_form, "Ошибка БД", str(e))

    def delete_product(self):
        msg = QMessageBox(self.w_product_form)
        msg.setWindowTitle('Удаление')
        msg.setText("Удалить этот товар?")
        msg.setIcon(QMessageBox.Question)
        btn_yes = msg.addButton("Да", QMessageBox.YesRole)
        msg.addButton("Нет", QMessageBox.NoRole)
        msg.exec()

        if msg.clickedButton() == btn_yes:
            try:
                check = self.db.fetch_one("SELECT COUNT(*) as count FROM order_items WHERE product_id=%s", (self.current_product_id,))
                if check and check['count'] > 0:
                    return QMessageBox.warning(self.w_product_form, "Запрет", "Этот товар есть в оформленных заказах, его нельзя удалить!")

                self.db.execute_query("DELETE FROM products WHERE id=%s", (self.current_product_id,))
                self.load_products()
                self.w_product_form.close()
            except Exception as e:
                QMessageBox.critical(self.w_product_form, "Ошибка", str(e))

    # ЗАКАЗЫ (МЕНЕДЖЕР / АДМИН)
    def open_orders_list(self):
        role = self.user['role'].strip()
        self.w_order_list.setWindowTitle("Список заказов")
        self.w_order_list.btnAddOrder.setVisible(role == 'Администратор')
        self.load_orders()
        self.w_order_list.show()

    def load_orders(self):
        layout = self.w_order_list.verticalLayout_2
        for i in reversed(range(layout.count())):
            widget = layout.itemAt(i).widget()
            if widget:
                layout.removeWidget(widget)
                widget.deleteLater()

        orders = self.db.fetch_all("""
            SELECT o.order_id, o.order_date, o.delivery_date, s.name as status, p.address 
            FROM orders o 
            LEFT JOIN order_statuses s ON o.status_id = s.status_id 
            LEFT JOIN pickup_points p ON o.pickup_point_id = p.pickup_point_id 
            ORDER BY o.order_date DESC""")

        role = self.user['role'].strip()
        for o in orders:
            w = self.loader.load('ui/order_item.ui')
            w.lblArticle.setText(f"<b>Артикул: {o['order_id']}</b>")
            w.lblStatus.setText(f"Статус: {o['status']}")
            w.lblAddress.setText(f"Адрес: {o['address']}")
            w.lblOrderDate.setText(f"Дата: {o['order_date']}")
            w.lblDeliveryDate.setText(f"Доставка:\n{o['delivery_date'] or 'Нет'}")

            # Привязка фильтра кликов для Администратора
            if role == 'Администратор':
                w.setCursor(Qt.PointingHandCursor)
                w.click_filter = ClickFilter(o['order_id'], self.open_edit_order)
                w.installEventFilter(w.click_filter)

            layout.addWidget(w)

    def open_add_order(self):
        self.current_order_id = None
        self.w_order_form.setWindowTitle("Добавить заказ")
        self.w_order_form.btnDeleteOrder.setVisible(False)
        self.w_order_form.comboBox.clear()
        self.w_order_form.comboBox_2.clear()

        for s in self.db.fetch_all("SELECT name FROM order_statuses"): self.w_order_form.comboBox.addItem(s['name'])
        for p in self.db.fetch_all("SELECT address FROM pickup_points"): self.w_order_form.comboBox_2.addItem(p['address'])

        self.w_order_form.lineEdit.setText("Автоматически")
        self.w_order_form.lineEdit.setReadOnly(True)

        # Устанавливаем даты по умолчанию
        current_date = QDate.currentDate()
        self.w_order_form.dateEdit.setDate(current_date)
        self.w_order_form.dateEdit_2.setMinimumDate(current_date)
        self.w_order_form.dateEdit_2.setDate(current_date.addDays(3))

        self.w_order_form.show()

    def open_edit_order(self, order_id):
        self.current_order_id = order_id
        self.w_order_form.setWindowTitle("Редактировать заказ")
        self.w_order_form.btnDeleteOrder.setVisible(True)
        self.w_order_form.comboBox.clear()
        self.w_order_form.comboBox_2.clear()

        for s in self.db.fetch_all("SELECT name FROM order_statuses"): self.w_order_form.comboBox.addItem(s['name'])
        for p in self.db.fetch_all("SELECT address FROM pickup_points"): self.w_order_form.comboBox_2.addItem(p['address'])

        order = self.db.fetch_one("""
            SELECT o.*, s.name as status, p.address 
            FROM orders o 
            LEFT JOIN order_statuses s ON o.status_id = s.status_id 
            LEFT JOIN pickup_points p ON o.pickup_point_id = p.pickup_point_id 
            WHERE o.order_id = %s""", (self.current_order_id,))

        self.w_order_form.lineEdit.setText(str(order['order_id']))
        self.w_order_form.lineEdit.setReadOnly(True)
        self.w_order_form.comboBox.setCurrentText(order['status'])
        self.w_order_form.comboBox_2.setCurrentText(order['address'])

        order_date = QDate.fromString(str(order['order_date']), "yyyy-MM-dd")
        self.w_order_form.dateEdit.setDate(order_date)
        self.w_order_form.dateEdit_2.setMinimumDate(order_date)

        if order['delivery_date']:
            self.w_order_form.dateEdit_2.setDate(QDate.fromString(str(order['delivery_date']), "yyyy-MM-dd"))

        self.w_order_form.show()

    def save_order(self):
        st_id = self.db.fetch_one("SELECT status_id FROM order_statuses WHERE name=%s", (self.w_order_form.comboBox.currentText(),))['status_id']
        p_id = self.db.fetch_one("SELECT pickup_point_id FROM pickup_points WHERE address=%s", (self.w_order_form.comboBox_2.currentText(),))['pickup_point_id']
        o_date = self.w_order_form.dateEdit.date().toString("yyyy-MM-dd")
        d_date = self.w_order_form.dateEdit_2.date().toString("yyyy-MM-dd")

        p_code = random.randint(100, 999)
        u_id = self.user['user_id']

        try:
            if self.current_order_id is None:
                self.db.execute_query(
                    "INSERT INTO orders (order_date, delivery_date, status_id, pickup_point_id, user_id, pickup_code) VALUES (%s, %s, %s, %s, %s, %s)",
                    (o_date, d_date, st_id, p_id, u_id, p_code)
                )
            else:
                self.db.execute_query(
                    "UPDATE orders SET order_date=%s, delivery_date=%s, status_id=%s, pickup_point_id=%s WHERE order_id=%s",
                    (o_date, d_date, st_id, p_id, self.current_order_id)
                )
            self.load_orders()
            self.w_order_form.close()
        except Exception as e:
            QMessageBox.critical(self.w_order_form, "Ошибка", f"Не удалось сохранить заказ:\n{str(e)}")

    def delete_order(self):
        msg = QMessageBox(self.w_order_form)
        msg.setWindowTitle('Удаление')
        msg.setText("Удалить заказ?")
        msg.setIcon(QMessageBox.Question)
        btn_yes = msg.addButton("Да", QMessageBox.YesRole)
        msg.addButton("Нет", QMessageBox.NoRole)
        msg.exec()

        if msg.clickedButton() == btn_yes:
            self.db.execute_query("DELETE FROM orders WHERE order_id=%s", (self.current_order_id,))
            self.load_orders()
            self.w_order_form.close()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ShoeStoreApp()
    sys.exit(app.exec())