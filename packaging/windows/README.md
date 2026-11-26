# Distribuição Windows x64

O produto final é um `onedir` PyInstaller dentro de um instalador Inno Setup.
O usuário final não precisa de Python, WSL, Conda ou Tesseract instalado.
O instalador é por usuário, em `%LOCALAPPDATA%\Programs\HB2 Studio`, com atalhos
no menu Iniciar e desinstalação registrada no HKCU. Não solicita elevação.

## Reproduzir no Windows

Pré-requisitos de **compilação**: Windows 64 bits, PowerShell 5.1 ou superior e
internet. O script prepara CPython 3.12 Windows isolado via conda-forge; não exige
Python global, nem usa o Python do MSYS2/WSL para compilar. As ferramentas restantes são baixadas para uma pasta temporária;
nenhuma precisa ser instalada globalmente e não são necessárias no computador
que recebe o instalador.

No PowerShell, na raiz do projeto:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\build.ps1 -Smoke
```

O script instala as versões fixadas de PyInstaller, PySide6-Essentials (os
módulos Qt Core/Gui/Widgets utilizados), PDFium e das dependências Python em um
ambiente Windows isolado. Usa Pillow 13 e CPython 3.12, como requer a versão atual do pdfplumber. Não muda
o ambiente de desenvolvimento nem inclui os módulos Qt WebEngine desnecessários.

O Tesseract 5.5.4 Windows e suas DLLs redistribuíveis vêm do conda-forge. O
micromamba 2.10.0 é uma ferramenta portátil de compilação, com SHA-256 fixado;
não é redistribuído com o aplicativo. O modelo `por.traineddata` vem do
`tessdata_fast` incluído no pacote. Só o português e as configurações do OCR
são copiados. A variante sem LZO/GPL opcional do libarchive é fixada. Os binários
VC runtime necessários permanecem app-local.

O compilador Inno Setup 6.7.3 oficial é preparado com `/PORTABLE=1 /CURRENTUSER`,
sem atalhos ou registro de instalação da ferramenta. A assinatura Authenticode
do download é verificada. Seus binários não fazem parte do produto instalado.

A pasta `dist/windows/0.1.1-DATA_HORA/` contém:

- `HB2Studio/`: distribuição `onedir`, com `HB2Studio.exe` e `_internal/`;
- `HB2Studio-0.1.1-x64-Setup.exe`: instalador completo;
- `installer.sha256.txt`: hash do instalador;
- `downloads.sha256.txt`: hashes e URLs dos downloads de ferramentas;
- `python-resolved.txt`: versões Python efetivamente utilizadas;
- `tesseract-win64.explicit.txt`: lock dos pacotes nativos;
- `installer-smoke.txt`: resultado da checagem, quando usado `-Smoke`.

`build/windows/last-output.txt` informa o diretório produzido. Os artefatos,
binários e ambientes estão excluídos do Git. A cópia das fontes usa apenas o
pacote Python e a configuração de empacotamento; não inclui PDFs, fotos,
`resultados/`, testes ou metadados Git.

Para usar um diretório temporário específico:

```powershell
.\packaging\windows\build.ps1 -WorkRoot C:\HB2Build\execucao -Smoke
```

O lock nativo versionado é utilizado automaticamente quando presente. Para
reutilizar um lock explícito de outra compilação:

```powershell
.\packaging\windows\build.ps1 -NativeLock C:\caminho\tesseract-win64.explicit.txt
```

Não são executados testes ou PDFs de validação do motor durante a compilação.

## Checagem limitada do instalador

`-Smoke` instala **por usuário** no caminho normal, confere o registro de
desinstalação, o runtime OCR e os avisos de licença, abre o atalho real do menu
Iniciar, aguarda a janela **Extrair PDF** responder e fecha a janela normalmente.
Não seleciona PDF nem executa OCR. Deixa a instalação disponível para uso.
Se já existir uma instalação, interrompe a checagem antes de sobrescrevê-la.

Para conferir um instalador já compilado:

```powershell
.\packaging\windows\smoke.ps1 -Installer C:\caminho\HB2Studio-0.1.1-x64-Setup.exe -Report C:\caminho\installer-smoke.txt
```

O desinstalador remove os arquivos instalados, não as pastas de resultados que
forem escolhidas pelo usuário. Não há instalador de Python nem alteração do
PATH global. O executável usa um manifesto padrão sem elevação.

## Recursos e licenças

O hook de runtime configura `HB2_TESSERACT` e `TESSDATA_PREFIX` com caminhos
relativos a `_internal/`, nunca com caminhos da máquina de compilação. Os
processos de OCR não abrem uma janela de console. Ao abrir Excel/Explorer, a
preferência de DLLs do PyInstaller é temporariamente retirada do processo filho.

A instalação inclui `_internal/licenses/LEIA-ME.txt`, a licença do CPython,
os avisos das distribuições Python/Qt/PDFium, as licenças dos pacotes nativos e
as receitas correspondentes, com seus endereços upstream e hashes. A preparação
falha se um pacote que fornece DLLs perder seus avisos de licença. Qt/PySide são
ligados dinamicamente; não se impede a substituição das DLLs compatíveis para
os fins permitidos pela LGPL.

Fontes de referência:

- [PyInstaller: programas externos e DLLs](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#launching-external-programs-from-the-frozen-application)
- [Inno Setup: instalação sem privilégios](https://jrsoftware.org/inno-setup/documentation/topic_setup_privilegesrequired.htm)
- [Inno Setup: compilador portátil](https://jrsoftware.org/inno-setup/documentation/topic_technotes.htm)
- [Receita conda-forge do Tesseract e sua licença](https://github.com/conda-forge/tesseract-feedstock/blob/main/recipe/recipe.yaml)
- [Micromamba: distribuição Windows](https://mamba.readthedocs.io/en/latest/installation/micromamba-installation.html#windows)

Um cache opcional de wheels Windows pode ser fornecido com `-Wheelhouse C:\cache`.
Ele acelera compilações repetidas e é utilizado sem consultar o índice PyPI.
Esse cache deve conter também `pefile` e `pywin32-ctypes`, condicionais do Windows.

O ambiente isolado desativa somente os aliases ICU não versionados do próprio
cache de compilação, que colidem com a API ICU do Windows usada pelo Qt atual.
As DLLs ICU versionadas permanecem com o runtime nativo. Bibliotecas do Windows
não são alteradas. A importação dos módulos Qt é conferida antes de congelar;
nenhum PDF é processado nessa verificação de dependências.

## Correção 0.1.1 — processamento no Windows

A saída do Tesseract e os TSVs são lidos/gravados explicitamente em UTF-8, sem
usar a página de código CP1252 do Windows. A saída TSV é ativada diretamente
por parâmetro e sua estrutura é conferida antes da leitura. O pacote inclui
`configs/` e `tessconfigs/` da localização própria do Tesseract, que pode ser
diferente da pasta dos modelos de idioma.

Falhas técnicas deixam um registro local em `%LOCALAPPDATA%\HB2 Studio\logs\erros.log`,
sem captura de variáveis locais ou envio de dados. A tela informa a etapa, o tipo
da falha e o caminho desse registro. Uma instalação anterior pode ser atualizada
com o novo instalador. Para conferir explicitamente uma atualização local:

```powershell
.\packaging\windows\smoke.ps1 -Installer C:\caminho\HB2Studio-0.1.1-x64-Setup.exe -Report C:\caminho\installer-smoke.txt -AllowUpgrade
```
