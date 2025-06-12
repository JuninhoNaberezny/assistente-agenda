Pré-requisitos
Python 3.9 ou superior

Como Executar o Projeto Flask: 
Crie um Ambiente Virtual 
python -m venv venv
.\venv\Scripts\activate

Instale as Dependências:
pip install -r requirements.txt

python -m pip install --upgrade pip

Inicie o servidor Flask:
python -m flask run --port 5001




Rodar com sua própria Agenda Google

Pré-requisitos: Configurando a API do Google Calendar
Este é o passo mais importante para que o código funcione. Você precisará habilitar a API e obter as credenciais.

1.Habilitar a API do Google Calendar:

Acesse o Google Cloud Console: https://console.cloud.google.com/

Crie um novo projeto (ou use um existente).

Habilite a API do Google Calendar:

No menu de navegação, vá para "APIs & Services" > "Library".

Procure por "Google Calendar API" e clique em "Enable".

2.Crie as Credenciais:

Vá para "APIs & Services" > "Credentials".

Clique em "Create Credentials" > "OAuth client ID".

Se solicitado, configure a "OAuth consent screen" (tela de consentimento). Escolha "External" e preencha os campos obrigatórios (nome do app, seu email, etc.).

Para o tipo de aplicação ("Application type"), selecione "Desktop app".

Dê um nome para a credencial e clique em "Create".

Baixe o arquivo JSON:

Uma janela aparecerá com seu "Client ID" e "Client Secret". Clique em "DOWNLOAD JSON".

Renomeie este arquivo para credentials.json e salve-o na mesma pasta onde seu script Python será executado.

3.Google Gemini API (.env)

Vá para o Google AI Studio.

Clique em Create API key in new project.

Copie a chave de API gerada.

Abra o arquivo .env que você criou no Passo 3 e cole a chave no lugar de SUA_CHAVE_API_AQUI. O arquivo deve ficar assim (com sua chave real):