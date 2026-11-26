# HB2 Studio

Aplicação desktop e motor local de extração de crachás, com pareamento de frente
e verso, OCR complementar, fotos e exportação para Excel.

Para usar no Windows sem instalar Python, WSL ou Tesseract, consulte a
[distribuição com instalador](packaging/windows/README.md). As instruções de
execução pelo código-fonte abaixo destinam-se ao desenvolvimento.

## Abrir a aplicação desktop

Requer Python 3.10 ou superior. Na pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[desktop]"
.\.venv\Scripts\python.exe -m hb2_studio.desktop
```

No Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[desktop]"
.venv/bin/python -m hb2_studio.desktop
```

Em Ubuntu/Debian com interface X11, instale também as bibliotecas nativas do Qt
e o Tesseract, se ainda não estiverem presentes:

```bash
sudo apt install tesseract-ocr tesseract-ocr-por libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-util1 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-xkb1
```

A janela requer uma sessão gráfica (no WSL, WSLg ou outro servidor gráfico).

Após instalar o extra `desktop`, também é possível abrir com
`hb2-studio-desktop` no ambiente virtual ativo.

O OCR requer Tesseract instalado separadamente, com o idioma português (`por`).
O executável deve estar no `PATH`. Se estiver em outro local, indique-o ao abrir:

```powershell
.\.venv\Scripts\python.exe -m hb2_studio.desktop --tesseract "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

Outra opção é definir `HB2_TESSERACT` antes de iniciar o aplicativo. Se os dados
de idioma não estiverem no diretório padrão do Tesseract, configure também
`TESSDATA_PREFIX` apontando para a pasta que contém `por.traineddata`. No Linux,
instale os pacotes Tesseract e idioma português da sua distribuição. O aplicativo
informa quando o executável ou o idioma necessário não estiver disponível.

Na tela **Extrair PDF**:

1. Selecione ou arraste um único PDF. A quantidade de páginas aparece primeiro;
   a quantidade de pares aparece depois que o motor terminar o pareamento.
2. Escolha a pasta de saída e clique em **Processar**. A leitura do PDF e o
   processamento usam uma tarefa em segundo plano. A etapa atual e a contagem
   real de crachás concluídos são atualizadas sem bloquear a janela.
3. Ao concluir, confira o total de crachás, os registros com pendências e a
   prévia de nome de guerra, nome completo, matrícula e situação. Use
   **Abrir planilha** ou **Abrir pasta de fotos** para acessar os resultados.

Cada execução cria uma subpasta `HB2Studio-DATA_HORA` dentro da pasta escolhida,
com `crachas.xlsx`, `fotos/`, `valores-combinados.json` e os intermediários. As abas
`Crachás` e `Revisão`, os links relativos e o formato texto de matrícula e PIS
são preservados pelo exportador existente. Mantenha a planilha junto de `fotos/`.
Para trabalhar nesta pasta de código, escolha `resultados/`, já ignorada pelo Git.

Em caso de falha, a tela mostra uma mensagem e permite tentar novamente ou
selecionar outro PDF/pasta. Arquivos com pareamento inválido não são exportados
parcialmente como um lote concluído. Ao fechar durante uma tarefa, o aplicativo
solicita a interrupção e aguarda a etapa atual terminar, sem encerrar a thread
à força. Não há histórico, integração com CorelDRAW ou instalador nesta versão.

A interface está em `hb2_studio/desktop.py`; o fluxo independente de Qt está em
`hb2_studio/pipeline.py` e chama os extratores e o exportador existentes. O fluxo
não depende de uma contagem fixa de 163 pares. O comando de terminal de
diagnóstico continua disponível, sem alterações:

## Executar no Windows

Na pasta do projeto, com Python 3.10 ou superior instalado:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m hb2_studio "C:\caminho\crachas.pdf" --esperados 163
```

O comando retorna código 2 se houver grupos rejeitados ou se a contagem esperada divergir. Código 1 indica uma falha de leitura.

## Como o motor trabalha

- Valida os grupos consecutivos (1–2, 3–4 etc.) pela posição da foto na frente e dos ícones no verso, incluindo a variante deslocada presente na amostra. Marca pares invertidos, páginas de layout desconhecido e páginas sem par para revisão.
- Recorta as regiões do nome da frente e do nome, admissão, matrícula, PIS e tipo sanguíneo do verso. As regiões em pontos PDF ficam em `hb2_studio/layout.py` e foram medidas nas páginas com texto selecionável da amostra.
- Compara os nomes quando os dois lados têm valor. Aceita nomes de exibição cujas palavras aparecem na mesma ordem no nome completo, inclusive quando há palavras omitidas. A comparação é uma indicação para revisão e a validação por layout confirma a ordem dos lados.
- Sinaliza páginas sem texto selecionável como candidatas a OCR. Um campo vazio em página com texto recebe `revisar_campo`, pois pode estar em branco ou exigir outro método de leitura.

Para integração local, use `from hb2_studio.engine import analyze_pdf`. Cada item em `analyze_pdf(caminho).badges` tem `front.values` e `back.values`. Os campos mantêm o texto original e os zeros à esquerda. Guarde PDFs e resultados com dados pessoais fora do repositório.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Os testes geram PDFs sintéticos temporários com o mesmo arranjo básico.

## Validação na amostra

O diagnóstico local processou 326 páginas e validou a ordem dos lados nos 163 pares, sem grupos rejeitados. Os nomes da frente e do verso foram compatíveis nos 43 pares com texto selecionável. Os 120 pares restantes foram sinalizados como candidatos a OCR.

Nos 43 versos com texto, a extração retornou 43 nomes, 43 datas de admissão, 43 matrículas e 19 valores de PIS. O tipo sanguíneo apareceu como rótulo, sem valor extraível. O projeto foi verificado com pdfplumber, disponível no ambiente local.

## Piloto OCR local

`tools/pilot_ocr.py` aceita somente 6 a 10 versos sem texto selecionável,
selecionados explicitamente por `--pages`. Requer Tesseract com `por` instalado.
Não realiza OCR em lote nem altera o fluxo de extração direta.

```bash
python tools/pilot_ocr.py pedido-novembro.pdf --pages 4 6 8 90 148 208 266 322
```

A saída fica obrigatoriamente em `resultados/`, ignorado pelo Git. Inclui imagens,
recortes, TSVs e leituras privadas; o terminal recebe apenas agregados. Valores
permanecem strings, preservando zeros iniciais, sem conversão numérica nem
correções automáticas. Duas passagens em escalas/modos diferentes sinalizam
inconsistências; confiança abaixo de 85, vazios e formatos inesperados exigem
revisão. Concordância entre passagens não comprova exatidão. No layout deslocado,
os recortes usam os rótulos detectados; ausência de âncora exige revisão.

Não publique nem adicione os artefatos privados ao controle de versão. A pasta
`.git` desta sessão está vazia, portanto não é possível auditar arquivos já
rastreados; as regras de exclusão existentes cobrem o PDF e `resultados/`.

Resultado do piloto local: 8 versos candidatos a OCR, sendo 3 do layout original
(todos os candidatos desse layout) e 5 distribuídos pelo layout deslocado. Em
40 recortes, a verificação geométrica por caixas de palavras detectou 2 possíveis
cortes em nomes, sinalizados para revisão. Isso não substitui inspeção visual.
As duas passagens concordaram em 5 nomes, 8 admissões, 8 matrículas e 3 PIS
preenchidos. Outros 5 PIS e os 8 tipos sanguíneos ficaram vazios, sem confirmação
de ausência. Cinco leituras preservaram zero inicial. Pelo critério conservador
de confiança mínima de 85 (incluindo rótulos), somente 2 nomes ficaram como
`consistente_ocr`; os outros 38 campos requerem revisão. Não há acurácia medida
contra transcrição humana, e o piloto não habilita processamento em lote.

O script compilou com sucesso. A suíte existente não pôde executar neste ambiente
por ausência de `reportlab`, dependência opcional de testes.

## OCR complementar integrado

O motor mantém a extração direta e permite habilitar OCR somente nas páginas
selecionadas explicitamente pela API. O comando de diagnóstico continua sem OCR
por padrão. Requer executável Tesseract e dados do idioma português (`por`).

```python
from hb2_studio.engine import analyze_pdf

result = analyze_pdf(
    "pedido-novembro.pdf",
    ocr_pages=[4, 6, 8, 90, 148, 208, 266, 322],
    ocr_output="resultados/minha-validacao-privada",
    tesseract="tesseract",
)
```

Somente versos reconhecidos entram no OCR. Campos já preenchidos pelo pdfplumber
são preservados; apenas os vazios recebem o complemento. `back.values` continua
contendo strings. `back.details[campo]` informa `origem` (`pdfplumber`, `ocr` ou
`sem_valor`), `status`, motivos em `reasons`, alternativa da passagem B, confiança
e caixa utilizada quando disponíveis. Vazio após OCR significa ausência não
confirmada. Erros de execução ficam como `ocr_indisponivel` e exigem revisão.
O diagnóstico público contém estados, origens e alertas, sem valores pessoais.

A implementação compartilhada está em `hb2_studio/ocr.py`; o piloto importa esse
mesmo extrator. Mantém nomes em duas linhas, acentos, hífens e zeros iniciais.
As coordenadas originais e deslocadas foram preservadas, incluindo a expansão
superior de 25 pixels nos nomes com linha acima do rótulo. As duas passagens não
fazem correções automáticas e não substituem conferência visual. Em particular,
a divergência de OCR anteriormente observada na página 208 não foi corrigida
por adivinhação. Campos de baixa confiança, divergentes, vazios ou com formato
inesperado continuam sinalizados.

A validação limitada a 20 versos é reproduzível com `tools/validate_ocr.py`.
Ela cria uma pasta privada nova em `resultados/` e executa o motor, sem exportador
ou interface. A seleção inclui os oito versos anteriores e 12 novos distribuídos
pelo layout deslocado. Os três candidatos do layout original já fazem parte
dos oito anteriores, portanto não existem candidatos novos desse layout.
O lote completo permanece desabilitado por padrão; não há opção de lote na CLI.

Validação da integração: 9 testes aprovados. O motor reconheceu os 163 pares
sem rejeições e aplicou OCR somente nos 20 versos selecionados (3 originais,
17 deslocados). Os 40 valores dos oito versos anteriores permaneceram iguais.
Foram preenchidos 20 nomes, 20 admissões, 20 matrículas e 3 PIS; 17 PIS e 20 tipos
sanguíneos permaneceram vazios, sem confirmação. Nove valores mantiveram zero
inicial. Quatro nomes satisfizeram o critério conservador de consistência;
os outros 96 campos exigem revisão. Todas as 20 páginas têm pelo menos um
alerta. Esses números validam a integração e não são uma medida de acurácia
contra transcrição humana dos 100 campos. A página 208 continua sinalizada.

## Processamento local do documento completo

Após a autorização de processamento completo, execute:

```bash
python tools/process_document.py pedido-novembro.pdf --esperados 163 --tesseract tesseract
```

O comando cria uma pasta nova com data e hora em `resultados/`, sem modificar
as execuções anteriores. Valida os pares pela extração direta e aplica OCR
complementar em todos os versos com campos vazios, inclusive os que têm outros
campos com texto selecionável. Confere que todos os valores diretos permaneceram
iguais. O JSON contém frente, verso, valores como strings, origem e alertas.
A folha de revisão em PDF inclui somente campos com alertas, com o nome direto
da frente como referência separada quando disponível. A referência nunca
substitui nem completa o trecho legível do nome do verso.

A promoção de `possivel_corte_de_texto` para `nome_incompleto_na_origem` exige um
registro visual explícito vinculado ao hash SHA-256 do documento. Sem esse
registro, o alerta continua sendo uma suspeita para conferência. A opção
`--confirmacoes` recebe um JSON privado com `documento_sha256`,
`confirmado_visualmente: true`, `motivo: "nome_incompleto_na_origem"` e uma lista
`paginas` de números de verso confirmados. Nenhum nome é inferido ou corrigido.
Os testes cobrem esse vínculo, a preservação dos fragmentos e a referência
separada na folha PDF. O terminal exibe apenas caminhos e contagens.

## Exportação XLSX a partir do JSON existente

Instale a dependência opcional com `python -m pip install -e ".[xlsx]"` e execute:

```bash
python tools/export_xlsx.py resultados/documento-completo-DATA_HORA/valores-finais.json
```

O comando cria uma planilha nova com data e hora dentro de `resultados/`, sem
abrir o PDF ou executar OCR. Não sobrescreve arquivos existentes. A aba `Crachás`
tem uma linha por par e a aba `Revisão` tem uma linha por campo sinalizado,
incluindo campos da frente. Vários motivos do mesmo campo permanecem juntos,
separados por quebras de linha. A situação do par considera todos esses alertas.
O nome exportado é o trecho do verso já salvo no JSON, sem completar pelo nome
da frente. Motivos como `nome_incompleto_na_origem` são preservados literalmente.

Matrícula e PIS são escritos como células de texto com formato `@`. Valores
nulos e strings vazias ficam em branco; identificadores numéricos no JSON são
rejeitados, pois seus zeros já podem ter sido perdidos. Valores que começam com
`=` também são gravados como texto literal. Após salvar, o exportador reabre
o arquivo e compara todas as células, tipos, contagens e motivos com a fonte.
O terminal informa somente o caminho e as contagens. Sem o JSON, a exportação
é interrompida; não há reconstrução dos dados a partir do PDF.

## Frente e verso na mesma linha

`hb2_studio/front.py` extrai o nome de guerra e a foto da frente. Reutiliza o texto
selecionável de `nome_frente` e aplica duas passagens de OCR em português quando
não há valor direto. As regiões calibradas são `(5,209,150,232)` no layout original
e `(7,239,140,263)` no deslocado, em pontos PDF. O tratamento remove o rótulo,
resíduos pequenos do rótulo e bordas, mantendo caixa, acentos, hífens e o trecho
legível. Vazios, ilegíveis, baixa confiança, divergências e possível corte geram
pendências. Comparações com o verso não completam nem corrigem o nome de guerra.
O motor aceita `front_ocr_pages` e `front_output` como opções explícitas da API;
o comportamento padrão de extração direta é preservado.

A foto usa o mesmo candidato geométrico que reconhece a frente no motor. A imagem
nativa só é aproveitada sem máscara e quando a proporção e a aparência coincidem
com a região renderizada. A comparação usa miniaturas de 160×200, erro médio RGB
até 4 e até 2% dos pixels com diferença maior que 30. Se máscara, recorte,
transformação ou outra diferença impedirem essa equivalência, salva-se a região
visível renderizada. Fotos sem candidato ou com candidatos ambíguos são
sinalizadas. Os recortes ficam separados do nome e do logotipo do crachá.

Após conferir uma amostra dos dois layouts:

```bash
python tools/combine_fronts.py pedido-novembro.pdf resultados/documento-completo-DATA_HORA/valores-finais.json
```

O comando verifica o hash do PDF e os lados dos pares já salvos, sem refazer OCR
de verso. Uma nova pasta privada contém `valores-combinados.json`, `crachas.xlsx`,
`fotos/` e os intermediários. Os 815 campos do verso são comparados integralmente
com a origem. A aba `Crachás` passa a conter `Nome completo` do verso, `Nome de
guerra`, `Foto` e as páginas de ambos os lados, mantendo os demais campos.
A aba `Revisão` inclui também as pendências da frente e da foto. As fotos têm
nomes pela página da frente e links relativos; mova o Excel junto com `fotos/`.
Ao reabrir o Excel, são conferidos todos os valores, tipos, links e a abertura de
cada imagem correspondente. Matrícula e PIS continuam como texto, com formato `@`.

## Instalador Windows 64 bits

A configuração `onedir` do PyInstaller e o instalador por usuário do Inno Setup
estão em [`packaging/windows/`](packaging/windows/README.md). A instalação final
inclui Qt, Python, Tesseract, português e licenças, sem requisitos separados de
Python/WSL/OCR no computador do usuário.

Para compilar e conferir apenas instalação e abertura pelo atalho, use o
PowerShell do Windows, na raiz deste projeto:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\packaging\windows\build.ps1 -Smoke
```

As instruções de reprodução, pré-requisitos exclusivos da máquina de compilação,
localização do instalador e registros da checagem estão no guia acima. Os arquivos
de distribuição ficam em `dist/`, fora do controle de versão. A compilação não
inclui PDFs de clientes, fotos ou resultados e não reexecuta a validação do motor.
