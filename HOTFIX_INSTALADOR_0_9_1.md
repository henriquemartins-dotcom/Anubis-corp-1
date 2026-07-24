# Hotfix do instalador - Hórus Connective 0.9.2

Correção do caminho do ícone no script do Inno Setup. O caractere de controle que aparecia na linha `SetupIconFile` foi removido e o caminho correto passou a ser `..\assets\horus.ico`.

Também foi adicionado um teste automático para impedir que caracteres de controle inválidos voltem a ser incluídos no arquivo `.iss`.
