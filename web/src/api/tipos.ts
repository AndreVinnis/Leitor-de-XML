// Contratos tipados à mão -- a maioria das rotas da API não declara
// response_model (só app/api/routes_casos.py o faz), então o OpenAPI não
// tem schema de resposta para gerar isso automaticamente. Ver a seção 1.3
// do plano de migração (fora de escopo desta fase, tratar como dívida).

export interface UsuarioLogado {
  id: number;
  email: string;
  nome: string;
  role: "comum" | "administrador";
  status_cadastro: "pendente" | "aprovado" | "reprovado";
  is_active: boolean;
  is_superuser: boolean;
  is_verified: boolean;
}

export interface LoginResposta {
  access_token: string;
  token_type: string;
}

export interface ClienteCaso {
  id: number;
  nome_cliente: string;
  identificacao_caso: string | null;
  criado_em: string;
}

export interface EstatisticasDashboard {
  notas_processadas: number;
  pendentes: number;
  erros: number;
}

export type StatusNota = "pendente" | "sucesso" | "erro" | "duplicado";

export type TipoNota = "entrada" | "saida";

export interface NotaResumo {
  id: number;
  numero: string | null;
  tipo: TipoNota | null;
  emitente_nome: string | null;
  destinatario_nome: string | null;
  data_emissao: string | null;
  // Decimal serializado como string pela API -- nunca number. Formatar na
  // exibição, nunca fazer conta com esse campo direto no front.
  valor_total: string | null;
  status: StatusNota | null;
}

export interface ListaNotas {
  itens: NotaResumo[];
  total: number;
}

export interface UploadNotasResposta {
  status: string;
  lote_id: string;
  total_arquivos: number;
  task_ids: string[];
}

export interface ArquivoLoteProgresso {
  id: number;
  nome_arquivo: string;
  status: StatusNota | null;
  motivo_erro: string | null;
  nota_id: number | null;
}

export interface ProgressoLote {
  lote_id: string;
  total_arquivos: number;
  concluidos: number;
  com_erro: number;
  arquivos: ArquivoLoteProgresso[];
}
