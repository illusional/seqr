import { combineReducers } from 'redux'
import { reducer as formReducer, SubmissionError } from 'redux-form'

import { reducers as dashboardReducers } from 'pages/Dashboard/reducers'
import { reducers as projectReducers } from 'pages/Project/reducers'
import { reducers as searchReducers } from 'pages/Search/reducers'
import { reducers as dataManagementReducers } from 'pages/DataManagement/reducers'
import { reducers as reportReducers } from 'pages/Report/reducers'
import { reducers as summaryDataReducers } from 'pages/SummaryData/reducers'
import { SORT_BY_XPOS } from 'shared/utils/constants'
import { HttpRequestHelper, getUrlQueryString } from 'shared/utils/httpRequestHelper'
import {
  createObjectsByIdReducer, loadingReducer, zeroActionsReducer, createSingleObjectReducer, createSingleValueReducer,
} from './utils/reducerFactories'
import modalReducers from './utils/modalReducer'
import {
  RECEIVE_DATA, REQUEST_PROJECTS, RECEIVE_SAVED_SEARCHES, REQUEST_SAVED_SEARCHES, REQUEST_SAVED_VARIANTS,
  REQUEST_SEARCHED_VARIANTS, RECEIVE_SEARCHED_VARIANTS, updateEntity,
} from './utils/reducerUtils'

/**
 * Action creator and reducers in one file as suggested by https://github.com/erikras/ducks-modular-redux
 */

// actions
const REQUEST_GENES = 'REQUEST_GENES'
const REQUEST_GENE_LISTS = 'REQUEST_GENE_LISTS'
const REQUEST_GENE_LIST = 'REQUEST_GENE_LIST'
const REQUEST_SEARCH_GENE_BREAKDOWN = 'REQUEST_SEARCH_GENE_BREAKDOWN'
const RECEIVE_SEARCH_GENE_BREAKDOWN = 'RECEIVE_SEARCH_GENE_BREAKDOWN'
const UPDATE_SEARCHED_VARIANT_DISPLAY = 'UPDATE_SEARCHED_VARIANT_DISPLAY'
const REQUEST_USER_OPTIONS = 'REQUEST_USER_OPTIONS'
const RECEIVE_USER_OPTIONS = 'RECEIVE_USER_OPTIONS'
const UPDATE_USER = 'UPDATE_USER'
const REQUEST_HPO_TERMS = 'REQUEST_HPO_TERMS'
const RECEIVE_HPO_TERMS = 'RECEIVE_HPO_TERMS'

// action creators

export const fetchProjects = () => (dispatch) => {
  dispatch({ type: REQUEST_PROJECTS })
  new HttpRequestHelper('/api/dashboard',
    (responseJson) => {
      dispatch({ type: RECEIVE_DATA, updatesById: responseJson })
    },
    e => dispatch({ type: RECEIVE_DATA, error: e.message, updatesById: {} })).get()
}

export const loadUserOptions = analystsOnly => (dispatch) => {
  const url = analystsOnly ? '/api/users/get_analyst_options' : '/api/users/get_options'
  dispatch({ type: REQUEST_USER_OPTIONS })
  new HttpRequestHelper(url,
    (responseJson) => {
      dispatch({ type: RECEIVE_USER_OPTIONS, newValue: responseJson })
    },
    (e) => {
      dispatch({ type: RECEIVE_USER_OPTIONS, error: e.message, newValue: [] })
    }).get()
}

export const loadAnalystOptions = () => loadUserOptions(true)

export const updateUser = values => dispatch => new HttpRequestHelper('/api/users/update',
  (responseJson) => {
    dispatch({ type: UPDATE_USER, updates: responseJson })
  },
  (e) => {
    throw new SubmissionError({ _error: [e.message] })
  }).post(values)

export const updateProject = (values) => {
  const actionSuffix = values.projectField ? `_project_${values.projectField}` : '_project'
  return updateEntity(values, RECEIVE_DATA, '/api/project', 'projectGuid', actionSuffix)
}

export const updateFamily = (values) => {
  const urlBase = `/api/family/${values.familyGuid}`
  if (values.nestedField) {
    return updateEntity(values, RECEIVE_DATA, `${urlBase}/${values.nestedField}`, `${values.nestedField}Guid`)
  }

  const familyField = values.familyField ? `_${values.familyField}` : ''
  return dispatch => new HttpRequestHelper(`${urlBase}/update${familyField}`,
    (responseJson) => {
      dispatch({ type: RECEIVE_DATA, updatesById: { familiesByGuid: responseJson } })
    },
    (e) => {
      throw new SubmissionError({ _error: [e.message] })
    }).post(values)
}

export const updateIndividual = values => (dispatch) => {
  const individualField = values.individualField ? `_${values.individualField}` : ''
  return new HttpRequestHelper(`/api/individual/${values.individualGuid}/update${individualField}`,
    (responseJson) => {
      dispatch({ type: RECEIVE_DATA, updatesById: { individualsByGuid: responseJson } })
    },
    (e) => {
      throw new SubmissionError({ _error: [e.message] })
    }).post(values)
}

export const loadGene = geneId => (dispatch, getState) => {
  const gene = getState().genesById[geneId]
  if (!gene || !gene.notes) {
    dispatch({ type: REQUEST_GENES })
    new HttpRequestHelper(`/api/gene_info/${geneId}`,
      (responseJson) => {
        dispatch({ type: RECEIVE_DATA, updatesById: responseJson })
      },
      (e) => {
        dispatch({ type: RECEIVE_DATA, error: e.message, updatesById: {} })
      }).get()
  }
}

export const loadGenes = geneIds => (dispatch, getState) => {
  const state = getState()
  if ([...geneIds].some(geneId => !state.genesById[geneId])) {
    dispatch({ type: REQUEST_GENES })
    new HttpRequestHelper('/api/genes_info',
      (responseJson) => {
        dispatch({ type: RECEIVE_DATA, updatesById: responseJson })
      },
      (e) => {
        dispatch({ type: RECEIVE_DATA, error: e.message, updatesById: {} })
      }).get({ geneIds: [...geneIds] })
  }
}

export const loadLocusLists = () => (dispatch) => {
  dispatch({ type: REQUEST_GENE_LISTS })
  new HttpRequestHelper('/api/locus_lists',
    (responseJson) => {
      dispatch({ type: RECEIVE_DATA, updatesById: responseJson })
    },
    (e) => {
      dispatch({ type: RECEIVE_DATA, error: e.message, updatesById: {} })
    }).get()
}

export const loadLocusListItems = locusListId => (dispatch, getState) => {
  if (!locusListId) {
    return
  }
  const locusList = getState().locusListsByGuid[locusListId]
  const isLoaded = locusList && locusList.items &&
    (!locusList.paLocusList || locusList.items.some(({ pagene }) => pagene))
  if (!isLoaded) {
    dispatch({ type: REQUEST_GENE_LIST })
    new HttpRequestHelper(`/api/locus_lists/${locusListId}`,
      (responseJson) => {
        dispatch({ type: RECEIVE_DATA, updatesById: responseJson })
      },
      (e) => {
        const updates = { locusListsByGuid: { [locusListId]: { items: [] } } }
        dispatch({ type: RECEIVE_DATA, error: e.message, updatesById: updates })
      }).get()
  }
}

export const loadHpoTerms = hpoId => (dispatch, getState) => {
  if (!getState().hpoTermsByParent[hpoId]) {
    dispatch({ type: REQUEST_HPO_TERMS })
    new HttpRequestHelper(`/api/hpo_terms/${hpoId}`,
      (responseJson) => {
        dispatch({ type: RECEIVE_HPO_TERMS, updatesById: responseJson })
      },
      (e) => {
        dispatch({ type: RECEIVE_HPO_TERMS, error: e.message, updatesById: {} })
      }).get()
  }
}

export const updateGeneNote = values => updateEntity(
  values, RECEIVE_DATA, `/api/gene_info/${values.geneId || values.gene_id}/note`, 'noteGuid',
)

export const navigateSavedHashedSearch = (search, navigateSearch, resultsPath) => (dispatch) => {
  // lazy load object-hash library as it is not used anywhere else
  import('object-hash').then((hash) => {
    const searchHash = hash.default.MD5(search)
    dispatch({ type: RECEIVE_SAVED_SEARCHES, updatesById: { searchesByHash: { [searchHash]: search } } })
    navigateSearch(`${resultsPath || '/variant_search/results'}/${searchHash}`)
  })
}

export const loadSearchedVariants = (
  { searchHash }, { displayUpdates, queryParams, updateQueryParams },
) => (dispatch, getState) => {
  const state = getState()
  if (state.searchedVariantsLoading.isLoading) {
    return
  }

  dispatch({ type: REQUEST_SEARCHED_VARIANTS })

  let { sort, page } = displayUpdates || queryParams
  if (!page) {
    page = 1
  }
  if (!sort) {
    sort = state.variantSearchDisplay.sort || SORT_BY_XPOS
  }
  const apiQueryParams = { sort: sort.toLowerCase(), page }

  // Update search table state and query params
  dispatch({ type: UPDATE_SEARCHED_VARIANT_DISPLAY, updates: { sort: sort.toUpperCase(), page } })
  updateQueryParams(apiQueryParams)

  const url = `/api/search/${searchHash}?${getUrlQueryString(apiQueryParams)}`
  const search = state.searchesByHash[searchHash]

  // Fetch variants
  new HttpRequestHelper(url,
    (responseJson) => {
      dispatch({ type: RECEIVE_DATA, updatesById: responseJson })
      dispatch({ type: RECEIVE_SEARCHED_VARIANTS, newValue: responseJson.searchedVariants })
      dispatch({ type: RECEIVE_SAVED_SEARCHES, updatesById: { searchesByHash: { [searchHash]: responseJson.search } } })
    },
    (e) => {
      dispatch({ type: RECEIVE_SEARCHED_VARIANTS, error: e.message, newValue: [] })
    }).post(search)
}

export const unloadSearchResults = () => dispatch => dispatch({ type: RECEIVE_SEARCHED_VARIANTS, newValue: [] })

export const loadGeneBreakdown = searchHash => (dispatch, getState) => {
  if (!getState().searchGeneBreakdown[searchHash]) {
    dispatch({ type: REQUEST_SEARCH_GENE_BREAKDOWN })

    new HttpRequestHelper(`/api/search/${searchHash}/gene_breakdown`,
      (responseJson) => {
        dispatch({ type: RECEIVE_DATA, updatesById: responseJson })
        dispatch({ type: RECEIVE_SEARCH_GENE_BREAKDOWN, updatesById: responseJson })
      },
      (e) => {
        dispatch({ type: RECEIVE_SEARCH_GENE_BREAKDOWN, error: e.message, updatesById: {} })
      }).get()
  }
}

const updateSavedVariant = (values, action = 'create') => (dispatch, getState) => new HttpRequestHelper(
  `/api/saved_variant/${action}`,
  (responseJson) => {
    dispatch({ type: RECEIVE_DATA, updatesById: responseJson })
  },
  (e) => {
    throw new SubmissionError({ _error: [e.message] })
  },
).post({ searchHash: getState().currentSearchHash, ...values })

export const updateVariantNote = (values) => {
  if (values.variantGuids) {
    return updateEntity(values, RECEIVE_DATA, `/api/saved_variant/${values.variantGuids}/note`, 'noteGuid')
  }
  return updateSavedVariant(values)
}

export const updateVariantTags = (values, tagType = 'tags') => {
  const urlPath = values.variantGuids ? `${values.variantGuids}/update_${tagType}` : 'create'
  return updateSavedVariant(values, urlPath)
}

export const updateVariantClassification = values => updateSavedVariant(values, `${values.variant.variantGuid}/update_acmg_classification`)

export const updateVariantMainTranscript = (variantGuid, transcriptId) => dispatch => new HttpRequestHelper(
  `/api/saved_variant/${variantGuid}/update_transcript/${transcriptId}`,
  (responseJson) => {
    dispatch({ type: RECEIVE_DATA, updatesById: responseJson })
  },
  (e) => {
    throw new SubmissionError({ _error: [e.message] })
  },
).post()

export const updateLocusList = values => (dispatch) => {
  let action = 'create'
  if (values.locusListGuid) {
    action = `${values.locusListGuid}/${values.delete ? 'delete' : 'update'}`
  }

  return new HttpRequestHelper(`/api/locus_lists/${action}`,
    (responseJson) => {
      dispatch({ type: RECEIVE_DATA, updatesById: responseJson })
    },
    (e) => {
      let error = e.message.replace('(400)', '')
      if (e.body && e.body.invalidLocusListItems) {
        error = `${error} Invalid genes/ intervals: ${e.body.invalidLocusListItems.join(', ')}`
      }
      throw new SubmissionError({
        _error: [error],
      })
    }).post(values)
}

// root reducer
const rootReducer = combineReducers({
  projectCategoriesByGuid: createObjectsByIdReducer(RECEIVE_DATA, 'projectCategoriesByGuid'),
  projectsByGuid: createObjectsByIdReducer(RECEIVE_DATA, 'projectsByGuid'),
  projectsLoading: loadingReducer(REQUEST_PROJECTS, RECEIVE_DATA),
  familiesByGuid: createObjectsByIdReducer(RECEIVE_DATA, 'familiesByGuid'),
  familyNotesByGuid: createObjectsByIdReducer(RECEIVE_DATA, 'familyNotesByGuid'),
  individualsByGuid: createObjectsByIdReducer(RECEIVE_DATA, 'individualsByGuid'),
  samplesByGuid: createObjectsByIdReducer(RECEIVE_DATA, 'samplesByGuid'),
  igvSamplesByGuid: createObjectsByIdReducer(RECEIVE_DATA, 'igvSamplesByGuid'),
  analysisGroupsByGuid: createObjectsByIdReducer(RECEIVE_DATA, 'analysisGroupsByGuid'),
  mmeSubmissionsByGuid: createObjectsByIdReducer(RECEIVE_DATA, 'mmeSubmissionsByGuid'),
  mmeResultsByGuid: createObjectsByIdReducer(RECEIVE_DATA, 'mmeResultsByGuid'),
  genesById: createObjectsByIdReducer(RECEIVE_DATA, 'genesById'),
  pagenesById: createObjectsByIdReducer(RECEIVE_DATA, 'pagenesById'),
  genesLoading: loadingReducer(REQUEST_GENES, RECEIVE_DATA),
  hpoTermsByParent: createObjectsByIdReducer(RECEIVE_HPO_TERMS),
  hpoTermsLoading: loadingReducer(REQUEST_HPO_TERMS, RECEIVE_HPO_TERMS),
  locusListsByGuid: createObjectsByIdReducer(RECEIVE_DATA, 'locusListsByGuid'),
  locusListsLoading: loadingReducer(REQUEST_GENE_LISTS, RECEIVE_DATA),
  locusListLoading: loadingReducer(REQUEST_GENE_LIST, RECEIVE_DATA),
  savedVariantsByGuid: createObjectsByIdReducer(RECEIVE_DATA, 'savedVariantsByGuid'),
  savedVariantsLoading: loadingReducer(REQUEST_SAVED_VARIANTS, RECEIVE_DATA),
  variantTagsByGuid: createObjectsByIdReducer(RECEIVE_DATA, 'variantTagsByGuid'),
  variantNotesByGuid: createObjectsByIdReducer(RECEIVE_DATA, 'variantNotesByGuid'),
  variantFunctionalDataByGuid: createObjectsByIdReducer(RECEIVE_DATA, 'variantFunctionalDataByGuid'),
  searchesByHash: createObjectsByIdReducer(RECEIVE_SAVED_SEARCHES, 'searchesByHash'),
  searchedVariants: createSingleValueReducer(RECEIVE_SEARCHED_VARIANTS, []),
  searchedVariantsLoading: loadingReducer(REQUEST_SEARCHED_VARIANTS, RECEIVE_SEARCHED_VARIANTS),
  searchGeneBreakdown: createObjectsByIdReducer(RECEIVE_SEARCH_GENE_BREAKDOWN, 'searchGeneBreakdown'),
  searchGeneBreakdownLoading: loadingReducer(REQUEST_SEARCH_GENE_BREAKDOWN, RECEIVE_SEARCH_GENE_BREAKDOWN),
  savedSearchesByGuid: createObjectsByIdReducer(RECEIVE_SAVED_SEARCHES, 'savedSearchesByGuid'),
  savedSearchesLoading: loadingReducer(REQUEST_SAVED_SEARCHES, RECEIVE_SAVED_SEARCHES),
  user: createSingleObjectReducer(UPDATE_USER),
  newUser: zeroActionsReducer,
  userOptionsByUsername: createSingleValueReducer(RECEIVE_USER_OPTIONS, {}),
  userOptionsLoading: loadingReducer(REQUEST_USER_OPTIONS, RECEIVE_USER_OPTIONS),
  meta: zeroActionsReducer,
  form: formReducer,
  variantSearchDisplay: createSingleObjectReducer(UPDATE_SEARCHED_VARIANT_DISPLAY, {
    sort: SORT_BY_XPOS,
    page: 1,
    recordsPerPage: 100,
  }, false),
  ...modalReducers,
  ...dashboardReducers,
  ...projectReducers,
  ...searchReducers,
  ...reportReducers,
  ...dataManagementReducers,
  ...summaryDataReducers,
})

export default rootReducer
