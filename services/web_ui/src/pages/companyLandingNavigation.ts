export function navigateToCompany(targetInn: string, locationRef: Pick<Location, 'assign'> = window.location) {
  locationRef.assign(`/company/${targetInn}`)
}
