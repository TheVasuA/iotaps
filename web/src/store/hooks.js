import { useDispatch, useSelector } from "react-redux";

// Thin re-exports. In a TS codebase these would be typed; kept as plain hooks
// here so feature code imports from one place.
export const useAppDispatch = () => useDispatch();
export const useAppSelector = useSelector;
