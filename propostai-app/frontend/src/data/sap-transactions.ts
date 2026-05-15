/**
 * Dados de transacoes SAP, atividades e codigo ABAP para o DetailModal.
 * Migrado de DETAIL_DATA do index.html legado.
 */

export interface Transaction { code: string; desc: string }
export interface CodeExample { title: string; lang: string; code: string }
export interface DetailEntry {
  icon: string; color: string; label: string
  transactions: Transaction[]
  activities: string[]
  codeExamples?: CodeExample[]
}

export const DETAIL_DATA: Record<string, DetailEntry> = {
  SD: {
    icon: '📦', color: '#3B7BF8', label: 'Consultor SD — Sales & Distribution',
    transactions: [
      { code: 'VA01', desc: 'Criar pedido de venda' }, { code: 'VA02', desc: 'Modificar pedido' },
      { code: 'VL01N', desc: 'Criar remessa/entrega' }, { code: 'VF01', desc: 'Criar fatura' },
      { code: 'VF11', desc: 'Cancelar fatura' }, { code: 'J1BNFE', desc: 'Monitor NF-e' },
      { code: 'J1B3N', desc: 'NF-e saida manual' }, { code: 'VOFM', desc: 'Formulas de copia' },
      { code: 'VOV8', desc: 'Categorias de item' }, { code: 'VTFL', desc: 'Copia pedido → fatura' },
      { code: 'VK11', desc: 'Criar condicao de preco' },
    ],
    activities: [
      'Configurar tipo de documento de venda (ZOR, ZRE, ZDV)',
      'Mapear categorias de item (TAN, TANN)',
      'Configurar sequencias de acesso e esquema de precos (pricing)',
      'Configurar determinacao de impostos — Grupo YA / cBenef',
      'Configurar BAdI para NF-e de saida (LE_SHP_DELIVERY_PROC)',
      'Configurar fluxo de faturamento e copia de documentos',
      'Integrar com modulo FI — lancamento contabil automatico',
      'Configurar NF-e (J1BNFE) e XMLs',
      'Testes integrados: pedido → entrega → NF-e → faturamento',
      'Documentacao funcional e KT',
    ],
  },
  FI: {
    icon: '💰', color: '#0D9488', label: 'Consultor FI — Financial Accounting',
    transactions: [
      { code: 'FB01', desc: 'Lancamento contabil' }, { code: 'F110', desc: 'Pagamento automatico' },
      { code: 'F-28', desc: 'Entrada de pagamento (AR)' }, { code: 'F-53', desc: 'Saida de pagamento (AP)' },
      { code: 'FBL1N', desc: 'Razao de fornecedores' }, { code: 'FBL5N', desc: 'Razao de clientes' },
      { code: 'FF67', desc: 'Extrato bancario eletronico' }, { code: 'FEBAN', desc: 'Monitor extrato' },
      { code: 'FS00', desc: 'Plano de contas' }, { code: 'OB52', desc: 'Periodos contabeis' },
    ],
    activities: [
      'Configurar contas do razao (FS00) e plano de contas',
      'Configurar pagamento automatico (F110) — bancos, formas pgto',
      'Configurar conciliacao bancaria eletronica (FF67/FEBAN)',
      'Configurar baixa automatica de titulos',
      'Configurar trigger ECONF (evento 110750 / 110751)',
      'Mapear impostos retidos (IRRF, PIS, COFINS, CSLL)',
      'Integrar com SD (faturamento → contabilizacao)',
      'Testes de ciclo completo',
    ],
  },
  GP: {
    icon: '📋', color: '#818CF8', label: 'Gerente de Projetos',
    transactions: [
      { code: 'SOLAR01', desc: 'Solution Manager — Blueprint' },
      { code: 'SOLAR02', desc: 'Solution Manager — Config' },
      { code: 'SE09', desc: 'Transportes (workbench)' }, { code: 'STMS', desc: 'Sistema de transporte' },
    ],
    activities: [
      'Elaborar e manter o cronograma detalhado',
      'Conduzir reunioes de status semanais',
      'Gerenciar escopo, riscos, issues e change requests',
      'Coordenar alocacao dos 3 ABAPers em paralelo',
      'Acompanhar deploys e promocao entre ambientes (DEV/QAS/PRD)',
      'Preparar relatorios de progresso',
      'Conduzir reuniao de go-live readiness e handover AMS',
    ],
  },
  ABAP: {
    icon: '⌨️', color: '#D97706', label: 'Desenvolvedor ABAP',
    transactions: [
      { code: 'SE38', desc: 'Editor ABAP' }, { code: 'SE24', desc: 'Class Builder' },
      { code: 'SE37', desc: 'Function Builder' }, { code: 'SE80', desc: 'Object Navigator' },
      { code: 'SE11', desc: 'Dicionario de dados' }, { code: 'SE18', desc: 'BAdI Definition' },
      { code: 'SE19', desc: 'BAdI Implementation' }, { code: 'SM30', desc: 'Manutencao de tabelas' },
      { code: 'SM37', desc: 'Monitor de jobs' }, { code: 'SICF', desc: 'Servicos HTTP/ICF' },
      { code: 'SLG1', desc: 'Log de aplicacao' }, { code: 'ST22', desc: 'Dumps ABAP' },
    ],
    activities: [
      'Desenvolver BAPI Z para integracao com hardware (TEF/POS)',
      'Implementar BAdI de NF-e para extensao XML fiscal (cBenef, tpIntegra)',
      'Desenvolver RFC Z para comunicacao entre sistemas',
      'Criar iFlow CPI para eventos ECONF 110750/110751',
      'Desenvolver Monitor Z para acompanhamento de integracoes',
      'Criar tabelas Z de parametrizacao (beneficios fiscais, regras por UF)',
      'Implementar jobs de carga/conciliacao em batch (SM37)',
      'Testes unitarios e de integracao de todos os objetos ABAP',
      'Deploy via transportes (SE09/STMS) em DEV → QAS → PRD',
    ],
    codeExamples: [
      {
        title: 'BAPI Z — Integracao TEF/Maquininha',
        lang: 'ABAP',
        code: `<span style="color:#8B949E;font-style:italic">*&amp; ZBAPI_TEF_PAYMENT — Integracao com terminal TEF/POS</span>
<span style="color:#FF7B72">FUNCTION</span> <span style="color:#D2A8FF">ZBAPI_TEF_PAYMENT</span>.
  <span style="color:#FF7B72">IMPORTING</span>
    <span style="color:#FFA657">IV_BUKRS</span>      <span style="color:#FF7B72">TYPE</span> <span style="color:#79C0FF">BUKRS</span>
    <span style="color:#FFA657">IV_AMOUNT</span>     <span style="color:#FF7B72">TYPE</span> <span style="color:#79C0FF">WRBTR</span>
    <span style="color:#FFA657">IV_TERMINAL</span>   <span style="color:#FF7B72">TYPE</span> <span style="color:#79C0FF">CHAR20</span>
  <span style="color:#FF7B72">EXPORTING</span>
    <span style="color:#FFA657">EV_AUTH_CODE</span>  <span style="color:#FF7B72">TYPE</span> <span style="color:#79C0FF">CHAR10</span>
    <span style="color:#FFA657">ES_RETURN</span>     <span style="color:#FF7B72">TYPE</span> <span style="color:#79C0FF">BAPIRET2</span>.

  <span style="color:#FF7B72">DATA</span>: <span style="color:#FFA657">lv_json</span> <span style="color:#FF7B72">TYPE</span> <span style="color:#79C0FF">STRING</span>,
        <span style="color:#FFA657">lo_http</span> <span style="color:#FF7B72">TYPE REF TO</span> <span style="color:#79C0FF">IF_HTTP_CLIENT</span>.

  <span style="color:#8B949E">* Montar payload e chamar servico TEF</span>
  <span style="color:#FFA657">lv_json</span> = <span style="color:#D2A8FF">ZCL_TEF_HELPER</span>=&gt;<span style="color:#D2A8FF">BUILD_PAYLOAD</span>( ... ).
  <span style="color:#FF7B72">CALL METHOD</span> <span style="color:#79C0FF">CL_HTTP_CLIENT</span>=&gt;<span style="color:#D2A8FF">CREATE_BY_DESTINATION</span>
    <span style="color:#FF7B72">EXPORTING</span> <span style="color:#FFA657">destination</span> = <span style="color:#A5D6FF">'ZTEF_RFC_DEST'</span>
    <span style="color:#FF7B72">IMPORTING</span> <span style="color:#FFA657">client</span> = <span style="color:#FFA657">lo_http</span>.
  <span style="color:#FFA657">lo_http</span>-&gt;<span style="color:#D2A8FF">send</span>( ). <span style="color:#FFA657">lo_http</span>-&gt;<span style="color:#D2A8FF">receive</span>( ).
<span style="color:#FF7B72">ENDFUNCTION</span>.`,
      },
      {
        title: 'BAdI NF-e — cBenef / tpIntegra',
        lang: 'ABAP',
        code: `<span style="color:#8B949E;font-style:italic">*&amp; ZCL_IM_NFE_CBENEF — BAdI NF-e Saida</span>
<span style="color:#FF7B72">CLASS</span> <span style="color:#D2A8FF">ZCL_IM_NFE_CBENEF</span> <span style="color:#FF7B72">IMPLEMENTATION</span>.
  <span style="color:#FF7B72">METHOD</span> <span style="color:#D2A8FF">IF_EX_BADI_NFE_OUT~CHANGE_NFE_DATA</span>.
    <span style="color:#FF7B72">SELECT SINGLE</span> <span style="color:#FFA657">cbenef</span>
      <span style="color:#FF7B72">FROM</span> <span style="color:#79C0FF">ZCBENEF_UF</span>
      <span style="color:#FF7B72">WHERE</span> <span style="color:#FFA657">uf</span> = <span style="color:#FFA657">is_nfe_header</span>-<span style="color:#FFA657">emit_uf</span>
        <span style="color:#FF7B72">AND</span> <span style="color:#FFA657">ncm</span> = <span style="color:#FFA657">is_nfe_item</span>-<span style="color:#FFA657">ncm</span>.
    <span style="color:#FF7B72">IF</span> <span style="color:#FFA657">sy</span>-<span style="color:#FFA657">subrc</span> = 0.
      <span style="color:#FFA657">cs_nfe_item</span>-<span style="color:#FFA657">cbenef</span> = <span style="color:#FFA657">ls_cbenef</span>-<span style="color:#FFA657">cbenef</span>.
      <span style="color:#8B949E">* GO: IN 1.608/2025 exige tpIntegra = 1</span>
      <span style="color:#FF7B72">IF</span> <span style="color:#FFA657">lv_uf</span> = <span style="color:#A5D6FF">'GO'</span>.
        <span style="color:#FFA657">cs_nfe_item</span>-<span style="color:#FFA657">tpintegra</span> = <span style="color:#A5D6FF">'1'</span>.
      <span style="color:#FF7B72">ENDIF</span>.
    <span style="color:#FF7B72">ENDIF</span>.
  <span style="color:#FF7B72">ENDMETHOD</span>.
<span style="color:#FF7B72">ENDCLASS</span>.`,
      },
    ],
  },
  FISCAL: {
    icon: '📜', color: '#FB923C', label: 'Consultor Fiscal — Estadual/Federal',
    transactions: [
      { code: 'J1BTAX', desc: 'Manutencao impostos Brasil' }, { code: 'J1BNFE', desc: 'Monitor NF-e' },
      { code: 'SPRO', desc: 'Customizing fiscal' }, { code: 'FTXP', desc: 'Codigos de imposto' },
      { code: 'SM30', desc: 'Tabela Z de cBenef por UF' },
    ],
    activities: [
      'Mapear legislacao fiscal por UF (ICMS, RICMS, cBenef)',
      'Configurar IN 1.608/2025-GO — campo tpIntegra=1',
      'Mapear beneficios fiscais (cBenef) por NCM e UF',
      'Configurar tabela Z de parametrizacao',
      'Validar NT 2024.002 — novos campos NF-e',
      'Analisar impactos da Reforma Tributaria (IBS/CBS)',
      'Testes de emissao NF-e com cenarios fiscais completos',
    ],
  },
  DRC: {
    icon: '🔗', color: '#22D3EE', label: 'Consultor DRC / CPI',
    transactions: [
      { code: 'EDOC_COCKPIT', desc: 'Cockpit e-Document' }, { code: 'SPRO', desc: 'Customizing DRC/CPI' },
      { code: 'SLG1', desc: 'Log de aplicacao' },
    ],
    activities: [
      'Avaliar viabilidade DRC nativo vs. CPI por evento fiscal',
      'Configurar canais CPI para ECONF',
      'Criar iFlow CPI para ECONF 110750 (autorizacao)',
      'Criar iFlow CPI para ECONF 110751 (cancelamento)',
      'Configurar comunicacao SAP <-> SEFAZ via CPI',
      'Testes de ida e volta com SEFAZ (homologacao)',
    ],
  },
}

export function getDetailKey(frente: string): string {
  const f = frente.toUpperCase().trim()
  if (f.startsWith('ABAP')) return 'ABAP'
  if (f.startsWith('SD')) return 'SD'
  if (f.startsWith('FI')) return 'FI'
  if (f.startsWith('GP')) return 'GP'
  if (f.startsWith('FISCAL') || f.startsWith('FEST') || f.startsWith('FFED')) return 'FISCAL'
  if (f.startsWith('DRC') || f.startsWith('CPI')) return 'DRC'
  if (f.startsWith('COMER')) return 'GP'
  return f
}
