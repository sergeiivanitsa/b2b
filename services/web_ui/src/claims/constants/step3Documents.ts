export type Step3DocumentDefinition = {
  id: string
  label: string
  order: number
}

export const STEP3_DOCUMENTS: readonly Step3DocumentDefinition[] = [
  {
    id: 'pdf_claim',
    label:
      'проверенная опытным юристом и сформированная с соблюдением претензионного порядка досудебная претензия в PDF',
    order: 1,
  },
  {
    id: 'docx_claim',
    label: 'редактируемая версия досудебной претензии в формате DOCX',
    order: 2,
  },
  {
    id: 'cover_letter',
    label: 'сопроводительное письмо',
    order: 3,
  },
  {
    id: 'penalty_table',
    label: 'таблица расчета неустойки',
    order: 4,
  },
  {
    id: 'instructions',
    label: 'инструкция по дальнейшей работе с претензией',
    order: 5,
  },
] as const
