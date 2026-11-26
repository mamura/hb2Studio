"""Aplicação desktop: python -m hb2_studio.desktop."""
import argparse
from pathlib import Path
import sys

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QThread, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QTableView, QVBoxLayout, QWidget, QAbstractItemView,
)

from .runtime import external_application_environment
from .diagnostics import failure_message
from .pipeline import (
    Inspection, PipelineError, ProcessingResult, Progress, inspect_pdf, process_pdf,
)


class Worker(QObject):
    progress = Signal(object)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, action):
        super().__init__()
        self.action = action
        self.stage = "Iniciando"

    def notify(self, update):
        self.stage = update.stage
        self.progress.emit(update)

    @Slot()
    def run(self):
        try:
            result = self.action(self.notify,
                                 QThread.currentThread().isInterruptionRequested)
            self.succeeded.emit(result)
        except Exception as error:
            self.failed.emit(failure_message(error, self.stage))
        finally:
            self.finished.emit()


class PreviewModel(QAbstractTableModel):
    headers = ('Nome de guerra', 'Nome completo', 'Matrícula', 'Situação da revisão')

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = ()

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        row = self.rows[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return (row.display_name, row.full_name, row.registration, row.review)[index.column()]
        if role == Qt.ItemDataRole.ForegroundRole and index.column() == 3:
            return QColor('#9a6700' if row.review == 'Pendente' else '#18754a')
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                return self.headers[section]
            return str(section + 1)
        return None


class PDFDropArea(QFrame):
    selected = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('dropArea')
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        self.title = QLabel('Arraste um PDF para cá')
        self.title.setObjectName('dropTitle')
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint = QLabel('ou selecione um arquivo no computador')
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title)
        layout.addWidget(self.hint)
        self.setMinimumHeight(100)

    def dragEnterEvent(self, event):
        urls = event.mimeData().urls()
        if self.isEnabled() and len(urls) == 1 and urls[0].isLocalFile() and Path(urls[0].toLocalFile()).suffix.lower() == '.pdf':
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if self.isEnabled() and len(urls) == 1 and urls[0].isLocalFile():
            self.selected.emit(Path(urls[0].toLocalFile()))
            event.acceptProposedAction()
        else:
            event.ignore()


class MainWindow(QMainWindow):
    def __init__(self, *, tesseract=None):
        super().__init__()
        self.tesseract = tesseract
        self.pdf_path = None
        self.destination = None
        self.inspection = None
        self.result = None
        self._thread = None
        self._worker = None
        self._kind = None
        self._closing = False
        self._failed = False
        self._pages = None
        self._pairs = None
        self.setWindowTitle('HB2 Studio — Extrair PDF')
        self.resize(1050, 800)
        self.setMinimumSize(760, 620)
        self._build_ui()
        self._refresh_controls()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)
        brand = QLabel('HB2 STUDIO')
        brand.setObjectName('brand')
        layout.addWidget(brand)
        title = QLabel('Extrair PDF')
        title.setObjectName('pageTitle')
        layout.addWidget(title)
        description = QLabel('Selecione o PDF de crachás para reunir os dados da frente e do verso em uma planilha.')
        description.setWordWrap(True)
        layout.addWidget(description)
        self.drop = PDFDropArea()
        self.drop.selected.connect(self.select_pdf)
        layout.addWidget(self.drop)
        file_row = QHBoxLayout()
        self.file_name = QLabel('Nenhum PDF selecionado')
        self.file_name.setTextFormat(Qt.TextFormat.PlainText)
        self.file_name.setWordWrap(True)
        file_row.addWidget(self.file_name, 1)
        self.select_button = QPushButton('Selecionar PDF')
        self.select_button.clicked.connect(self.choose_pdf)
        file_row.addWidget(self.select_button)
        layout.addLayout(file_row)
        self.metadata = QLabel('As quantidades serão exibidas após a análise do arquivo.')
        self.metadata.setObjectName('muted')
        layout.addWidget(self.metadata)
        layout.addWidget(QLabel('Pasta de saída'))
        output_row = QHBoxLayout()
        self.output_path = QLineEdit()
        self.output_path.setReadOnly(True)
        self.output_path.setPlaceholderText('Escolha onde salvar a planilha e as fotos')
        output_row.addWidget(self.output_path, 1)
        self.folder_button = QPushButton('Escolher pasta')
        self.folder_button.clicked.connect(self.choose_output)
        output_row.addWidget(self.folder_button)
        layout.addLayout(output_row)
        process_row = QHBoxLayout()
        self.stage = QLabel('Selecione um PDF para começar.')
        self.stage.setWordWrap(True)
        process_row.addWidget(self.stage, 1)
        self.process_button = QPushButton('Processar')
        self.process_button.setObjectName('primary')
        self.process_button.clicked.connect(self.start_processing)
        process_row.addWidget(self.process_button)
        layout.addLayout(process_row)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)
        self.error_label = QLabel()
        self.error_label.setObjectName('error')
        self.error_label.setWordWrap(True)
        self.error_label.setTextFormat(Qt.TextFormat.PlainText)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        self.summary = QLabel('Prévia dos crachás')
        self.summary.setObjectName('sectionTitle')
        layout.addWidget(self.summary)
        self.preview_model = PreviewModel(self)
        self.preview = QTableView()
        self.preview.setModel(self.preview_model)
        self.preview.setAlternatingRowColors(True)
        self.preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.preview.verticalHeader().setVisible(False)
        self.preview.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.preview.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.preview.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.preview.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.preview, 1)
        actions = QHBoxLayout()
        self.result_path = QLabel()
        self.result_path.setTextFormat(Qt.TextFormat.PlainText)
        self.result_path.setWordWrap(True)
        self.result_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        actions.addWidget(self.result_path, 1)
        self.open_workbook = QPushButton('Abrir planilha')
        self.open_photos = QPushButton('Abrir pasta de fotos')
        self.open_workbook.clicked.connect(self.show_workbook)
        self.open_photos.clicked.connect(self.show_photos)
        actions.addWidget(self.open_workbook)
        actions.addWidget(self.open_photos)
        layout.addLayout(actions)
        self.setStyleSheet('''
            QMainWindow { background: #f5f7fb; }
            QWidget { font-size: 14px; color: #1d2939; }
            QLabel#brand { color: #2463c5; font-size: 13px; font-weight: 700; }
            QLabel#pageTitle { font-size: 28px; font-weight: 700; }
            QLabel#sectionTitle, QLabel#dropTitle { font-size: 16px; font-weight: 600; }
            QLabel#muted { color: #667085; }
            QLabel#error { color: #9e2424; background: #fff0ef; padding: 10px; border-radius: 6px; }
            QFrame#dropArea { border: 2px dashed #acbcd3; border-radius: 10px; background: #fff; }
            QPushButton { background: #fff; border: 1px solid #cbd4e1; border-radius: 6px; padding: 9px 15px; }
            QPushButton:hover { background: #edf3ff; }
            QPushButton:disabled { color: #98a2b3; background: #eef1f5; }
            QPushButton#primary { background: #2463c5; color: white; border: none; font-weight: 600; }
            QPushButton#primary:disabled { background: #c4d2e8; color: #eef3fa; }
            QLineEdit { background: white; border: 1px solid #cbd4e1; border-radius: 6px; padding: 9px; }
            QProgressBar { border: none; background: #e1e7f0; border-radius: 4px; max-height: 8px; }
            QProgressBar::chunk { background: #2463c5; border-radius: 4px; }
            QTableView { background: white; alternate-background-color: #f7f9fc; border: 1px solid #dbe2ec; gridline-color: #edf0f5; }
            QHeaderView::section { background: #edf1f7; border: none; padding: 10px; font-weight: 600; }
        ''')

    def _refresh_controls(self):
        busy = self._thread is not None
        self.select_button.setEnabled(not busy)
        self.drop.setEnabled(not busy)
        self.folder_button.setEnabled(not busy or self._kind == 'inspect')
        can_retry_inspection = self._failed and self.inspection is None and self.pdf_path is not None
        self.process_button.setEnabled(not busy and (can_retry_inspection or (self.inspection is not None and self.destination is not None)))
        self.process_button.setText('Tentar novamente' if self._failed else 'Processar novamente' if self.result else 'Processar')
        self.open_workbook.setEnabled(not busy and self.result is not None)
        self.open_photos.setEnabled(not busy and self.result is not None)

    @Slot()
    def choose_pdf(self):
        file_name, _ = QFileDialog.getOpenFileName(self, 'Selecionar PDF', '', 'Arquivos PDF (*.pdf *.PDF)')
        if file_name:
            self.select_pdf(Path(file_name))

    @Slot(object)
    def select_pdf(self, path):
        if self._thread is not None:
            return
        path = Path(path).expanduser().resolve()
        if path.suffix.lower() != '.pdf' or not path.is_file():
            QMessageBox.warning(self, 'Arquivo inválido', 'Selecione um arquivo PDF existente.')
            return
        self.pdf_path = path
        self.inspection = None
        self.result = None
        self._pages = self._pairs = None
        self.preview_model.set_rows(())
        self.summary.setText('Prévia dos crachás')
        self.result_path.clear()
        self.file_name.setText(path.name)
        self.file_name.setToolTip(str(path))
        self.metadata.setText('Contando páginas e identificando pares…')
        self._inspect_current()

    def _inspect_current(self):
        path = self.pdf_path
        self._start_job('inspect', lambda notify, cancelled: inspect_pdf(path, notify, cancelled))

    @Slot()
    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, 'Escolher pasta de saída', str(self.destination or Path.cwd() / 'resultados'))
        if folder:
            self.destination = Path(folder)
            self.output_path.setText(str(self.destination))
            self._refresh_controls()

    @Slot()
    def start_processing(self):
        if self._thread is not None:
            return
        if self.inspection is None:
            if self.pdf_path is not None:
                self._inspect_current()
            return
        if self.destination is None:
            return
        inspection, destination = self.inspection, self.destination
        self.result = None
        self.result_path.clear()
        self.preview_model.set_rows(())
        self.summary.setText('Prévia dos crachás')
        self._start_job('process', lambda notify, cancelled: process_pdf(
            inspection, destination, tesseract=self.tesseract, notify=notify, cancelled=cancelled))

    def _start_job(self, kind, action):
        self._failed = False
        self._kind = kind
        self.error_label.hide()
        self.stage.setText('Analisando PDF…' if kind == 'inspect' else 'Preparando processamento…')
        self.progress_bar.setRange(0, 0)
        thread = QThread(self)
        worker = Worker(action)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.on_progress)
        worker.succeeded.connect(self.on_success)
        worker.failed.connect(self.on_failure)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(self.on_finished)
        thread.finished.connect(thread.deleteLater)
        self._thread, self._worker = thread, worker
        self._refresh_controls()
        thread.start()

    @Slot(object)
    def on_progress(self, update: Progress):
        if self._closing:
            return
        if update.pages is not None:
            self._pages = update.pages
        if update.pairs is not None:
            self._pairs = update.pairs
        parts = []
        if self._pages is not None:
            parts.append(f'{self._pages} páginas')
        if self._pairs is not None:
            parts.append(f'{self._pairs} pares identificados')
        self.metadata.setText(' · '.join(parts))
        text = update.stage
        if update.processed is not None and update.pairs is not None:
            text += f' — {update.processed} de {update.pairs} crachás processados'
            self.progress_bar.setRange(0, max(1, update.pairs))
            self.progress_bar.setValue(update.processed)
        self.stage.setText(text)

    @Slot(object)
    def on_success(self, result):
        if self._closing:
            return
        if isinstance(result, Inspection):
            self.inspection = result
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)
            if result.document.rejected:
                self.stage.setText('PDF analisado. Há grupos de páginas que precisam de conferência.')
            elif not result.document.badges:
                self.stage.setText('PDF analisado. Nenhum par de crachá identificado.')
            else:
                self.stage.setText('PDF pronto. Clique em Processar.' if self.destination else 'PDF pronto. Escolha a pasta de saída e clique em Processar.')
        elif isinstance(result, ProcessingResult):
            self.result = result
            self.preview_model.set_rows(result.preview)
            self.progress_bar.setRange(0, max(1, result.total))
            self.progress_bar.setValue(result.total)
            self.stage.setText('Processamento concluído.')
            self.summary.setText(f'{result.total} crachás · {result.pending} registros com pendências')
            self.result_path.setText(str(result.output_dir))

    @Slot(str)
    def on_failure(self, message):
        if self._closing:
            return
        self._failed = True
        self.stage.setText('Não foi possível concluir. Você pode tentar novamente.')
        self.error_label.setText(message)
        self.error_label.show()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)

    @Slot()
    def on_finished(self):
        self._thread = self._worker = None
        self._kind = None
        self._refresh_controls()
        if self._closing:
            self.close()

    def _open_local(self, path):
        if not path.exists():
            QMessageBox.warning(self, 'Arquivo não encontrado', 'O resultado foi movido ou apagado. Processe o PDF novamente.')
        else:
            with external_application_environment():
                opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))
            if not opened:
                QMessageBox.warning(self, 'Não foi possível abrir', f'Abra este caminho no seu computador:\n{path}')

    @Slot()
    def show_workbook(self):
        if self.result:
            self._open_local(self.result.workbook)

    @Slot()
    def show_photos(self):
        if self.result:
            self._open_local(self.result.photo_dir)

    def closeEvent(self, event):
        if self._thread is not None:
            self._closing = True
            self._thread.requestInterruption()
            self.stage.setText('Encerrando após a etapa atual…')
            self.centralWidget().setEnabled(False)
            event.ignore()
        else:
            event.accept()


def main(argv=None):
    parser = argparse.ArgumentParser(description='HB2 Studio — aplicação desktop')
    parser.add_argument('--tesseract', help='Caminho opcional do executável Tesseract')
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    app.setApplicationName('HB2 Studio')
    app.setOrganizationName('HB2 Studio')
    app.setStyle('Fusion')
    window = MainWindow(tesseract=args.tesseract)
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
